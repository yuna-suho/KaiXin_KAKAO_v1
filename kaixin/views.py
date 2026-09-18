from datetime import datetime
import json

from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.timezone import make_aware, get_current_timezone
from django.views.decorators.http import require_http_methods, require_POST

from accounts.blacklist_store import (
    KIND_BOT,
    KIND_LABELS,
    KIND_LIMIT,
    KIND_LOGIN,
    KIND_MANUAL,
    KIND_MYBOX,
    KIND_RATE,
    KIND_UNKNOWN,
    add_blacklist_ip,
    clear_blacklist_entries,
    clear_blacklist_entries_for_kind,
    clear_mybox_visit_records,
    delete_mybox_visit_record,
    get_block_reasons,
    get_block_reasons_map,
    is_ip_blocked,
    is_local_ip,
    list_blacklist_entries,
    list_mybox_visit_counts,
    remove_blacklist_entry,
    remove_blacklist_ip,
)
from accounts.bot_detect import (
    BUILTIN_UA_KEYWORDS,
    add_path_keyword,
    add_ua_keyword,
    extra_path_keywords,
    extra_ua_keywords,
    remove_path_keyword,
    remove_ua_keyword,
)
from accounts.download_store import (
    clear_download_files,
    create_download_file,
    delete_download_file,
    download_max_bytes,
    format_byte_size,
    list_download_files,
)
from accounts.policy_store import (
    ensure_default_policy,
    get_blacklist_policy,
    get_mybox_display,
    reset_blacklist_policy_fields,
    reset_mybox_display,
    save_mybox_display,
    update_blacklist_policy,
)
from kaixin.auth import (
    PENDING_MESSAGE,
    get_current_admin,
    login_admin,
    login_required,
    logout_admin,
    superadmin_required,
)
from kaixin.store import (
    aggregate_logs_by_ip,
    count_admin_users,
    create_admin_user,
    delete_admin_user,
    delete_all_logs,
    delete_logs_for_ip,
    delete_logs_for_ips,
    export_request_logs,
    find_admin_by_username,
    format_request_data,
    format_timestamp,
    list_admin_users,
    list_logs_for_ip,
    list_methods_for_ip,
    list_pending_admins,
    set_admin_approval,
)


def _base_context(request, admin=None):
    admin = admin if admin is not None else getattr(request, 'kaixin_admin', None)
    return {
        'admin': admin,
        'is_superadmin': bool(admin and admin.get('is_superadmin')),
    }


def _parse_export_datetime(raw_value):
    value = (raw_value or '').strip()
    if not value:
        return None
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            parsed = datetime.strptime(value, fmt)
            break
        except ValueError:
            parsed = None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = make_aware(parsed, get_current_timezone())
    return parsed


def _json_export_response(payload, filename):
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    response = HttpResponse(body, content_type='application/json; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _posted_ips(request):
    seen = set()
    cleaned = []
    for raw in request.POST.getlist('ips'):
        ip = (raw or '').strip()
        if not ip or ip in seen:
            continue
        seen.add(ip)
        cleaned.append(ip)
    return cleaned


def _block_ips(ips):
    for ip in ips:
        if not is_local_ip(ip):
            add_blacklist_ip(ip, KIND_MANUAL, note='manual block from request logs')


@require_http_methods(['GET', 'POST'])
def login_view(request):
    admin = get_current_admin(request)
    if admin is not None:
        if admin.get('is_approved'):
            return redirect('kaixin:dashboard')
        logout_admin(request)

    error = ''
    info = ''
    username = ''
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        user = find_admin_by_username(username) if username else None
        if user is None or not check_password(password, user.get('password_hash', '')):
            error = 'Invalid username or password.'
        elif not user.get('is_approved'):
            info = PENDING_MESSAGE
        else:
            login_admin(request, user)
            return redirect('kaixin:dashboard')

    return render(
        request,
        'kaixin/login.html',
        {
            'error': error,
            'info': info,
            'username': username,
            'has_admins': count_admin_users() > 0,
        },
    )


@require_http_methods(['GET', 'POST'])
def register_view(request):
    admin = get_current_admin(request)
    if admin is not None:
        if admin.get('is_approved'):
            return redirect('kaixin:dashboard')
        logout_admin(request)

    is_first = count_admin_users() == 0
    error = ''
    username = ''
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        password = request.POST.get('password') or ''
        password_confirm = request.POST.get('password_confirm') or ''

        if len(username) < 3:
            error = 'Username must be at least 3 characters.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif password != password_confirm:
            error = 'Passwords do not match.'
        else:
            created = create_admin_user(
                username,
                make_password(password),
                is_superadmin=is_first,
                is_approved=is_first,
            )
            if created is None:
                error = 'Username is already taken.'
            elif is_first:
                login_admin(request, created)
                return redirect('kaixin:dashboard')
            else:
                messages.info(request, PENDING_MESSAGE)
                return redirect('kaixin:login')

    return render(
        request,
        'kaixin/register.html',
        {'error': error, 'username': username, 'is_first': is_first},
    )


@require_POST
def logout_view(request):
    logout_admin(request)
    return redirect('kaixin:login')


@login_required
@require_http_methods(['GET', 'POST'])
def dashboard(request):
    if request.method == 'POST':
        action = request.POST.get('action') or ''
        ip = (request.POST.get('ip') or '').strip()
        selected_ips = _posted_ips(request)
        if ip and action == 'block':
            _block_ips([ip])
        elif ip and action == 'unblock':
            remove_blacklist_ip(ip)
        elif ip and action == 'delete':
            delete_logs_for_ip(ip)
        elif action == 'delete_all':
            delete_all_logs()
        elif action == 'block_selected':
            _block_ips(selected_ips)
        elif action == 'unblock_selected':
            for selected in selected_ips:
                remove_blacklist_ip(selected)
        elif action == 'delete_selected':
            delete_logs_for_ips(selected_ips)
        elif action == 'block_and_delete_selected':
            _block_ips(selected_ips)
            delete_logs_for_ips(selected_ips)
        return redirect('kaixin:dashboard')

    rows = []
    block_reasons = get_block_reasons_map()
    for item in aggregate_logs_by_ip():
        ip = item.get('_id') or 'unknown'
        local = is_local_ip(ip)
        reasons = [] if local else (block_reasons.get(ip) or [])
        rows.append(
            {
                'ip': ip,
                'count': item.get('count', 0),
                'last_seen': format_timestamp(item.get('last_seen')),
                'first_seen': format_timestamp(item.get('first_seen')),
                'devices': ', '.join(sorted(d for d in (item.get('devices') or []) if d))
                or '-',
                'is_local': local,
                'blocked': bool(reasons) or (not local and is_ip_blocked(ip)),
                'block_reasons': reasons,
                'block_reason': ', '.join(reasons) if reasons else '',
            }
        )
    context = _base_context(request)
    context['rows'] = _paginate(request, rows)
    return render(request, 'kaixin/dashboard.html', context)


@login_required
@require_http_methods(['GET'])
def export_logs_view(request):
    ip = (request.GET.get('ip') or '').strip() or None
    method = (request.GET.get('method') or '').strip().upper() or None
    since_raw = request.GET.get('since')
    until_raw = request.GET.get('until')
    since = _parse_export_datetime(since_raw)
    until = _parse_export_datetime(until_raw)
    if since_raw and since is None:
        return HttpResponse(
            'Invalid since datetime. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM.',
            status=400,
            content_type='text/plain; charset=utf-8',
        )
    if until_raw and until is None:
        return HttpResponse(
            'Invalid until datetime. Use YYYY-MM-DD or YYYY-MM-DDTHH:MM.',
            status=400,
            content_type='text/plain; charset=utf-8',
        )
    if since and until and since > until:
        return HttpResponse(
            'Since must be earlier than until.',
            status=400,
            content_type='text/plain; charset=utf-8',
        )

    logs = export_request_logs(ip=ip, method=method, since=since, until=until)
    exported_at = datetime.now(tz=get_current_timezone()).isoformat()
    payload = {
        'exported_at': exported_at,
        'filters': {
            'ip': ip,
            'method': method,
            'since': since.isoformat() if since else None,
            'until': until.isoformat() if until else None,
        },
        'count': len(logs),
        'logs': logs,
    }
    stamp = datetime.now(tz=get_current_timezone()).strftime('%Y%m%d_%H%M%S')
    scope = (ip or 'all').replace(':', '_').replace('/', '_')
    filename = f'request_logs_{scope}_{stamp}.json'
    return _json_export_response(payload, filename)


@login_required
@require_http_methods(['GET', 'POST'])
def ip_logs(request, ip):
    method_filter = (request.GET.get('method') or '').strip().upper()
    available_methods = list_methods_for_ip(ip)
    if method_filter and method_filter not in available_methods:
        method_filter = ''

    def _ip_logs_redirect():
        if method_filter:
            return redirect(f"{reverse('kaixin:ip_logs', kwargs={'ip': ip})}?method={method_filter}")
        return redirect('kaixin:ip_logs', ip=ip)

    if request.method == 'POST':
        action = request.POST.get('action') or ''
        if action == 'delete':
            delete_logs_for_ip(ip)
            return redirect('kaixin:dashboard')
        if action == 'block':
            if not is_local_ip(ip):
                add_blacklist_ip(ip, KIND_MANUAL, note='manual block from request logs')
            return _ip_logs_redirect()
        if action == 'unblock':
            remove_blacklist_ip(ip)
            return _ip_logs_redirect()

    logs = []
    for doc in list_logs_for_ip(ip, method=method_filter or None):
        logs.append(
            {
                'timestamp': format_timestamp(doc.get('timestamp')),
                'method': doc.get('method') or '-',
                'path': doc.get('path') or '-',
                'query': format_request_data(doc.get('query')),
                'body': format_request_data(doc.get('body')),
                'device': doc.get('device') or '-',
                'os': doc.get('os') or '-',
                'browser': doc.get('browser') or '-',
                'model': doc.get('model') or '-',
                'language': doc.get('language') or '-',
            }
        )
    context = _base_context(request)
    local = is_local_ip(ip)
    reasons = [] if local else get_block_reasons(ip)
    context.update(
        {
            'ip': ip,
            'logs': _paginate(request, logs),
            'is_local': local,
            'blocked': bool(reasons) or (not local and is_ip_blocked(ip)),
            'block_reasons': reasons,
            'block_reason': ', '.join(reasons) if reasons else '',
            'method_filter': method_filter,
            'available_methods': available_methods,
        }
    )
    return render(request, 'kaixin/ip_logs.html', context)


@superadmin_required
@require_http_methods(['GET', 'POST'])
def admins_view(request):
    if request.method == 'POST':
        admin_id = request.POST.get('admin_id') or ''
        action = request.POST.get('action') or ''
        if action == 'approve':
            set_admin_approval(admin_id, True)
        elif action == 'revoke':
            set_admin_approval(admin_id, False)
        elif action == 'delete':
            delete_admin_user(admin_id)
        return redirect('kaixin:admins')

    pending = []
    for user in list_pending_admins():
        pending.append(
            {
                'id': str(user['_id']),
                'username': user.get('username') or '-',
                'created_at': format_timestamp(user.get('created_at')),
            }
        )

    admins = []
    for user in list_admin_users():
        admins.append(
            {
                'id': str(user['_id']),
                'username': user.get('username') or '-',
                'is_superadmin': bool(user.get('is_superadmin')),
                'is_approved': bool(user.get('is_approved')),
                'created_at': format_timestamp(user.get('created_at')),
            }
        )

    context = _base_context(request)
    context.update({'pending': pending, 'admins': admins})
    return render(request, 'kaixin/admins.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def files_view(request):
    if request.method == 'POST':
        action = request.POST.get('action') or ''
        if action == 'save_policy':
            update_blacklist_policy(
                {
                    'download_redirect_url': request.POST.get('download_redirect_url'),
                }
            )
            messages.success(request, 'Download redirect saved.')
        elif action == 'reset_policy':
            reset_blacklist_policy_fields(['download_redirect_url'])
            messages.success(request, 'Download redirect reset.')
        elif action == 'upload':
            row, error = create_download_file(
                request.FILES.get('file'),
                filename=request.POST.get('filename'),
            )
            if error:
                messages.error(request, error)
            elif row:
                messages.success(request, f'Uploaded {row.filename}.')
        elif action == 'delete':
            if delete_download_file(request.POST.get('file_id')):
                messages.success(request, 'File deleted.')
            else:
                messages.error(request, 'File not found.')
        elif action == 'delete_all':
            deleted = clear_download_files()
            messages.success(request, f'Deleted {deleted} file(s).')
        return redirect('kaixin:files')

    files = []
    for item in list_download_files():
        files.append(
            {
                **item,
                'created_at': format_timestamp(item.get('created_at')),
                'absolute_url': request.build_absolute_uri(item['path']),
            }
        )

    context = _base_context(request)
    context.update(
        {
            'files': files,
            'max_size_label': format_byte_size(download_max_bytes()),
            'policy': get_blacklist_policy(),
        }
    )
    return render(request, 'kaixin/files.html', context)


BLACKLIST_SECTIONS = {
    'ips': {
        'redirect': 'kaixin:blacklist',
        'template': 'kaixin/blacklist.html',
        'fields': ('redirect_url',),
    },
    'limits': {
        'redirect': 'kaixin:blacklist_limits',
        'template': 'kaixin/blacklist_limits.html',
        'fields': (
            'limits_redirect_url',
            'rate_limit_enabled',
            'rate_limit_max_requests',
            'rate_limit_window_seconds',
            'total_request_limit_enabled',
            'total_request_limit_max',
        ),
    },
    'login': {
        'redirect': 'kaixin:blacklist_login',
        'template': 'kaixin/blacklist_login.html',
        'fields': (
            'login_redirect_url',
            'login_attempt_max',
            'login_loading_enabled',
            'login_loading_delay_ms',
            'login_loading_progress_percent',
            'login_loading_hold_ms',
            'login_splash_enabled',
            'login_splash_delay_ms',
            'login_intro_mode',
            'login_mybox_delay_ms',
        ),
    },
    'mybox': {
        'redirect': 'kaixin:blacklist_mybox',
        'template': 'kaixin/blacklist_mybox.html',
        'fields': (
            'mybox_visit_limit_enabled',
            'mybox_visit_max',
            'mybox_redirect_url',
        ),
    },
    'bots': {
        'redirect': 'kaixin:blacklist_bots',
        'template': 'kaixin/blacklist_bots.html',
        'fields': (
            'bot_block_enabled',
            'bot_redirect_url',
            'bot_block_empty_ua',
            'bot_block_scanner_paths',
            'bot_block_honeypot',
            'bot_block_webdriver',
            'bot_ua_keywords',
        ),
    },
    'unknown': {
        'redirect': 'kaixin:blacklist_unknown',
        'template': 'kaixin/blacklist_unknown.html',
        'fields': (
            'unknown_block_enabled',
            'unknown_redirect_url',
        ),
    },
}

_POLICY_BOOL_FIELDS = {
    'rate_limit_enabled',
    'total_request_limit_enabled',
    'login_loading_enabled',
    'login_splash_enabled',
    'mybox_visit_limit_enabled',
    'bot_block_enabled',
    'bot_block_empty_ua',
    'bot_block_scanner_paths',
    'bot_block_honeypot',
    'bot_block_webdriver',
    'unknown_block_enabled',
}

BLACKLIST_LIST_PAGE_SIZE = 25

SECTION_ENTRY_KINDS = {
    'ips': frozenset({KIND_MANUAL}),
    'limits': frozenset({KIND_RATE, KIND_LIMIT}),
    'login': frozenset({KIND_LOGIN}),
    'mybox': frozenset({KIND_MYBOX}),
    'bots': frozenset({KIND_BOT}),
    'unknown': frozenset({KIND_UNKNOWN}),
}


def _policy_updates_from_post(post, fields):
    updates = {}
    for field in fields:
        if field in _POLICY_BOOL_FIELDS:
            updates[field] = post.get(field) == 'on'
        elif field not in post:
            continue
        else:
            updates[field] = post.get(field)
    return updates


def _blacklist_entries(kind=None):
    entries = []
    for doc in list_blacklist_entries(kind=kind):
        entry_kind = doc.get('kind')
        entries.append(
            {
                'id': str(doc['_id']),
                'ip': doc.get('ip') or '-',
                'reason': KIND_LABELS.get(entry_kind, entry_kind or '-'),
            }
        )
    return entries


def _mybox_visit_rows():
    rows = []
    for row in list_mybox_visit_counts():
        rows.append(
            {
                'ip': row['ip'],
                'count': row['count'],
                'updated_at': format_timestamp(row['updated_at']),
                'blocked': row['blocked'],
            }
        )
    return rows


def _section_entry_kind(section, posted_kind):
    allowed = SECTION_ENTRY_KINDS.get(section) or frozenset()
    kind = (posted_kind or '').strip()
    if kind in allowed:
        return kind
    if len(allowed) == 1:
        return next(iter(allowed))
    return None


def _paginate(request, items, param='page', per_page=BLACKLIST_LIST_PAGE_SIZE):
    paginator = Paginator(items, per_page)
    page = paginator.get_page(request.GET.get(param))
    page.elided_pages = list(
        paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    )
    return page


def _paginated_entries(request, kind=None, param='page'):
    return _paginate(request, _blacklist_entries(kind=kind), param=param)


@login_required
@require_http_methods(['GET', 'POST'])
def blacklist_view(request, section='ips'):
    config = BLACKLIST_SECTIONS.get(section)
    if config is None:
        return redirect('kaixin:blacklist')

    error = ''
    redirect_name = config['redirect']
    if request.method == 'POST':
        action = request.POST.get('action') or ''
        if section == 'ips' and action == 'add':
            ip = (request.POST.get('ip') or '').strip()
            if not ip:
                error = 'IP address is required.'
            elif is_local_ip(ip):
                error = 'Local addresses cannot be blacklisted.'
            elif not add_blacklist_ip(ip, KIND_MANUAL, note='manual'):
                error = 'IP is already on this list (or could not be saved).'
            else:
                return redirect(redirect_name)
        elif action == 'delete':
            remove_blacklist_entry(request.POST.get('entry_id') or '')
            return redirect(redirect_name)
        elif section == 'ips' and action == 'remove_selected':
            for ip in _posted_ips(request):
                remove_blacklist_ip(ip)
            return redirect(redirect_name)
        elif section == 'ips' and action == 'delete_all_blacklist':
            clear_blacklist_entries()
            return redirect(redirect_name)
        elif action == 'remove_selected_kind':
            kind = _section_entry_kind(section, request.POST.get('entry_kind'))
            if kind:
                for ip in _posted_ips(request):
                    remove_blacklist_ip(ip, kind)
            return redirect(redirect_name)
        elif action == 'delete_all_kind':
            kind = _section_entry_kind(section, request.POST.get('entry_kind'))
            if kind:
                clear_blacklist_entries_for_kind(kind)
            return redirect(redirect_name)
        elif section == 'mybox' and action == 'delete_visit':
            delete_mybox_visit_record(request.POST.get('ip') or '')
            return redirect(redirect_name)
        elif section == 'mybox' and action == 'delete_selected_visits':
            for ip in _posted_ips(request):
                delete_mybox_visit_record(ip)
            return redirect(redirect_name)
        elif section == 'mybox' and action == 'delete_all_visits':
            clear_mybox_visit_records()
            return redirect(redirect_name)
        elif action == 'block_selected':
            kind = _section_entry_kind(section, request.POST.get('entry_kind'))
            if kind:
                for ip in _posted_ips(request):
                    if not is_local_ip(ip):
                        add_blacklist_ip(ip, kind, note='manual block from blacklist')
            return redirect(redirect_name)
        elif action == 'unblock_selected':
            kind = _section_entry_kind(section, request.POST.get('entry_kind'))
            if kind:
                for ip in _posted_ips(request):
                    remove_blacklist_ip(ip, kind)
            return redirect(redirect_name)
        elif section == 'bots' and action == 'add_ua_keyword':
            policy = ensure_default_policy()
            text, keyword_error = add_ua_keyword(
                policy.get('bot_ua_keywords'), request.POST.get('keyword')
            )
            if keyword_error:
                error = keyword_error
            elif update_blacklist_policy({'bot_ua_keywords': text}) is None:
                error = 'Failed to save keyword.'
            else:
                return redirect(redirect_name)
        elif section == 'bots' and action == 'delete_ua_keyword':
            policy = ensure_default_policy()
            text = remove_ua_keyword(
                policy.get('bot_ua_keywords'), request.POST.get('keyword')
            )
            if update_blacklist_policy({'bot_ua_keywords': text}) is None:
                error = 'Failed to delete keyword.'
            else:
                return redirect(redirect_name)
        elif section == 'bots' and action == 'delete_all_ua_keywords':
            if update_blacklist_policy({'bot_ua_keywords': ''}) is None:
                error = 'Failed to delete keywords.'
            else:
                return redirect(redirect_name)
        elif section == 'bots' and action == 'add_path_keyword':
            policy = ensure_default_policy()
            text, keyword_error = add_path_keyword(
                policy.get('bot_path_keywords'), request.POST.get('keyword')
            )
            if keyword_error:
                error = keyword_error
            elif update_blacklist_policy({'bot_path_keywords': text}) is None:
                error = 'Failed to save keyword.'
            else:
                return redirect(redirect_name)
        elif section == 'bots' and action == 'delete_path_keyword':
            policy = ensure_default_policy()
            text = remove_path_keyword(
                policy.get('bot_path_keywords'), request.POST.get('keyword')
            )
            if update_blacklist_policy({'bot_path_keywords': text}) is None:
                error = 'Failed to delete keyword.'
            else:
                return redirect(redirect_name)
        elif section == 'bots' and action == 'delete_all_path_keywords':
            if update_blacklist_policy({'bot_path_keywords': ''}) is None:
                error = 'Failed to delete keywords.'
            else:
                return redirect(redirect_name)
        elif section == 'mybox' and action == 'save_display':
            saved, display_error = save_mybox_display(
                filename=request.POST.get('mybox_filename'),
                filesize=request.POST.get('mybox_filesize'),
                page_title=request.POST.get('mybox_page_title'),
                image=request.FILES.get('mybox_image'),
            )
            if display_error:
                error = display_error
            elif saved is None:
                error = 'Failed to save MYBOX display settings.'
            else:
                return redirect(redirect_name)
        elif section == 'mybox' and action == 'reset_display':
            reset_mybox_display()
            return redirect(redirect_name)
        elif action == 'save_policy' and config['fields']:
            saved = update_blacklist_policy(
                _policy_updates_from_post(request.POST, config['fields'])
            )
            if saved is None:
                error = 'Failed to save policy settings.'
            else:
                return redirect(redirect_name)
        elif action == 'reset_policy' and config['fields']:
            if reset_blacklist_policy_fields(config['fields']) is None:
                error = 'Failed to reset policy settings.'
            else:
                return redirect(redirect_name)

    context = _base_context(request)
    context.update(
        {
            'blacklist_section': section,
            'error': error,
            'policy': ensure_default_policy(),
        }
    )
    if section == 'ips':
        context['entries'] = _paginated_entries(request, param='entries_page')
    elif section == 'limits':
        context['rate_entries'] = _paginated_entries(
            request, kind=KIND_RATE, param='rate_page'
        )
        context['limit_entries'] = _paginated_entries(
            request, kind=KIND_LIMIT, param='limit_page'
        )
    elif section == 'login':
        context['login_entries'] = _paginated_entries(request, kind=KIND_LOGIN)
    elif section == 'mybox':
        context['mybox_visits'] = _paginate(
            request, _mybox_visit_rows(), param='visits_page'
        )
        display = get_mybox_display()
        display['image_absolute_url'] = request.build_absolute_uri(display['image_url'])
        context['mybox_display'] = display
    elif section == 'bots':
        context['bot_entries'] = _paginated_entries(request, kind=KIND_BOT)
        context['builtin_ua_keywords'] = BUILTIN_UA_KEYWORDS
        context['extra_ua_keywords'] = extra_ua_keywords(context['policy'])
        context['extra_path_keywords'] = extra_path_keywords(context['policy'])
    elif section == 'unknown':
        context['unknown_entries'] = _paginated_entries(request, kind=KIND_UNKNOWN)
    return render(request, config['template'], context)
