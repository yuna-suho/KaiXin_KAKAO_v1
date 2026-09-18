import threading
import time
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction

from accounts.models import (
    MYBOX_IMAGE_DIR,
    MYBOX_IMAGE_STORED_STEM,
    BlacklistPolicy,
)

POLICY_DOC_ID = 'blacklist_policy'
DEFAULT_MYBOX_FILENAME = '20260824_071530'
DEFAULT_MYBOX_FILESIZE = '2MB'
DEFAULT_MYBOX_PAGE_TITLE = '긴급 상황: 신원 확인 부탁드립니다.'
DEFAULT_MYBOX_STATIC = 'mybox/images/viewer.jpg'
MYBOX_IMAGE_MAX_BYTES = 8 * 1024 * 1024
MYBOX_IMAGE_TYPES = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
}

DEFAULT_POLICY = {
    'redirect_url': 'https://www.naver.com/',
    'rate_limit_enabled': True,
    'rate_limit_max_requests': 80,
    'rate_limit_window_seconds': 60,
    'total_request_limit_enabled': True,
    'total_request_limit_max': 500,
    'login_attempt_max': 2,
    'login_loading_enabled': True,
    'login_loading_delay_ms': 3000,
    'login_loading_progress_percent': 100,
    'login_loading_hold_ms': 1000,
    'login_splash_enabled': True,
    'login_splash_delay_ms': 1000,
    'login_intro_mode': 'loading',
    'login_mybox_delay_ms': 3000,
    'mybox_visit_limit_enabled': True,
    'mybox_visit_max': 3,
    'mybox_redirect_url': 'https://www.naver.com/',
    'limits_redirect_url': 'https://www.naver.com/',
    'login_redirect_url': 'https://www.naver.com/',
    'bot_block_enabled': True,
    'bot_redirect_url': 'https://www.naver.com/',
    'bot_block_empty_ua': True,
    'bot_block_scanner_paths': True,
    'bot_block_honeypot': True,
    'bot_block_webdriver': True,
    'bot_ua_keywords': '',
    'bot_path_keywords': '',
    'unknown_block_enabled': True,
    'unknown_redirect_url': 'https://www.naver.com/',
    'download_redirect_url': 'https://www.naver.com/',
    'mybox_filename': DEFAULT_MYBOX_FILENAME,
    'mybox_filesize': DEFAULT_MYBOX_FILESIZE,
    'mybox_page_title': DEFAULT_MYBOX_PAGE_TITLE,
}

_cache_lock = threading.Lock()
_cache = {'loaded_at': 0.0, 'policy': None}


def _clean_mybox_filename(value, default=DEFAULT_MYBOX_FILENAME):
    text = str(value or '').strip().replace('\\', '/').split('/')[-1]
    suffix = Path(text).suffix.lower()
    if suffix in {'.jpg', '.jpeg', '.png', '.gif', '.webp'}:
        text = Path(text).stem
    text = text[:120].strip()
    return text or default


def _clean_mybox_filesize(value, default=DEFAULT_MYBOX_FILESIZE):
    text = str(value or '').strip()[:32]
    return text or default


def _clean_mybox_page_title(value, default=DEFAULT_MYBOX_PAGE_TITLE):
    text = str(value or '').strip()[:200]
    return text or default


def _validate_mybox_image(image):
    size = getattr(image, 'size', 0) or 0
    if size <= 0:
        return 'Image file is required.'
    if size > MYBOX_IMAGE_MAX_BYTES:
        return 'Image must be 8MB or smaller.'
    name = Path(getattr(image, 'name', '') or '').suffix.lower()
    if name == '.jpeg':
        name = '.jpg'
    content = (getattr(image, 'content_type', None) or '').lower()
    if name not in {'.jpg', '.png', '.gif', '.webp'} and content not in MYBOX_IMAGE_TYPES:
        return 'Use a JPG, PNG, GIF, or WebP image.'
    return None


def _defaults_from_django_settings():
    return {
        'redirect_url': getattr(settings, 'BLACKLIST_REDIRECT_URL', DEFAULT_POLICY['redirect_url']),
        'rate_limit_enabled': bool(getattr(settings, 'RATE_LIMIT_ENABLED', True)),
        'rate_limit_max_requests': int(getattr(settings, 'RATE_LIMIT_MAX_REQUESTS', 80)),
        'rate_limit_window_seconds': int(getattr(settings, 'RATE_LIMIT_WINDOW_SECONDS', 60)),
        'total_request_limit_enabled': bool(getattr(settings, 'TOTAL_REQUEST_LIMIT_ENABLED', True)),
        'total_request_limit_max': int(getattr(settings, 'TOTAL_REQUEST_LIMIT_MAX', 500)),
        'login_attempt_max': int(getattr(settings, 'LOGIN_ATTEMPT_MAX', 2)),
        'login_loading_enabled': bool(getattr(settings, 'LOGIN_LOADING_ENABLED', True)),
        'login_loading_delay_ms': int(getattr(settings, 'LOGIN_LOADING_DELAY_MS', 3000)),
        'login_loading_progress_percent': int(
            getattr(settings, 'LOGIN_LOADING_PROGRESS_PERCENT', 100)
        ),
        'login_loading_hold_ms': int(getattr(settings, 'LOGIN_LOADING_HOLD_MS', 1000)),
        'login_splash_enabled': bool(getattr(settings, 'LOGIN_SPLASH_ENABLED', True)),
        'login_splash_delay_ms': int(getattr(settings, 'LOGIN_SPLASH_DELAY_MS', 1000)),
        'login_intro_mode': str(getattr(settings, 'LOGIN_INTRO_MODE', 'loading')),
        'login_mybox_delay_ms': int(getattr(settings, 'LOGIN_MYBOX_DELAY_MS', 3000)),
        'mybox_visit_limit_enabled': bool(getattr(settings, 'MYBOX_VISIT_LIMIT_ENABLED', True)),
        'mybox_visit_max': int(getattr(settings, 'MYBOX_VISIT_MAX', 3)),
        'mybox_redirect_url': getattr(
            settings, 'MYBOX_REDIRECT_URL', DEFAULT_POLICY['mybox_redirect_url']
        ),
        'limits_redirect_url': getattr(
            settings, 'LIMITS_REDIRECT_URL', DEFAULT_POLICY['limits_redirect_url']
        ),
        'login_redirect_url': getattr(
            settings, 'LOGIN_ATTEMPT_REDIRECT_URL', DEFAULT_POLICY['login_redirect_url']
        ),
        'bot_block_enabled': bool(getattr(settings, 'BOT_BLOCK_ENABLED', True)),
        'bot_redirect_url': getattr(
            settings, 'BOT_REDIRECT_URL', DEFAULT_POLICY['bot_redirect_url']
        ),
        'bot_block_empty_ua': bool(getattr(settings, 'BOT_BLOCK_EMPTY_UA', True)),
        'bot_block_scanner_paths': bool(getattr(settings, 'BOT_BLOCK_SCANNER_PATHS', True)),
        'bot_block_honeypot': bool(getattr(settings, 'BOT_BLOCK_HONEYPOT', True)),
        'bot_block_webdriver': bool(getattr(settings, 'BOT_BLOCK_WEBDRIVER', True)),
        'bot_ua_keywords': str(getattr(settings, 'BOT_UA_KEYWORDS', '')),
        'bot_path_keywords': str(getattr(settings, 'BOT_PATH_KEYWORDS', '')),
        'unknown_block_enabled': bool(getattr(settings, 'UNKNOWN_BLOCK_ENABLED', True)),
        'unknown_redirect_url': getattr(
            settings, 'UNKNOWN_REDIRECT_URL', DEFAULT_POLICY['unknown_redirect_url']
        ),
        'download_redirect_url': getattr(
            settings, 'DOWNLOAD_REDIRECT_URL', DEFAULT_POLICY['download_redirect_url']
        ),
        'mybox_filename': str(getattr(settings, 'MYBOX_FILENAME', DEFAULT_MYBOX_FILENAME)),
        'mybox_filesize': str(getattr(settings, 'MYBOX_FILESIZE', DEFAULT_MYBOX_FILESIZE)),
        'mybox_page_title': str(
            getattr(settings, 'MYBOX_PAGE_TITLE', DEFAULT_MYBOX_PAGE_TITLE)
        ),
    }


def _normalize_policy(raw):
    base = _defaults_from_django_settings()
    if not isinstance(raw, dict):
        return dict(base)

    def as_url(key):
        value = str(raw.get(key) or base[key]).strip()
        return value or base[key]

    redirect_url = as_url('redirect_url')
    mybox_redirect_url = as_url('mybox_redirect_url')
    limits_redirect_url = as_url('limits_redirect_url')
    login_redirect_url = as_url('login_redirect_url')
    bot_redirect_url = as_url('bot_redirect_url')
    unknown_redirect_url = as_url('unknown_redirect_url')
    download_redirect_url = as_url('download_redirect_url')

    def as_bool(value, default):
        if isinstance(value, bool):
            return value
        if value in (0, 1, '0', '1', 'true', 'false', 'True', 'False', 'on', 'off'):
            return str(value).lower() in ('1', 'true', 'on')
        return default

    def as_int(value, default, minimum=1, maximum=None):
        try:
            number = int(value)
        except (TypeError, ValueError):
            return default
        number = max(minimum, number)
        if maximum is not None:
            number = min(maximum, number)
        return number

    return {
        'redirect_url': redirect_url,
        'rate_limit_enabled': as_bool(raw.get('rate_limit_enabled'), base['rate_limit_enabled']),
        'rate_limit_max_requests': as_int(
            raw.get('rate_limit_max_requests'), base['rate_limit_max_requests']
        ),
        'rate_limit_window_seconds': as_int(
            raw.get('rate_limit_window_seconds'), base['rate_limit_window_seconds']
        ),
        'total_request_limit_enabled': as_bool(
            raw.get('total_request_limit_enabled'), base['total_request_limit_enabled']
        ),
        'total_request_limit_max': as_int(
            raw.get('total_request_limit_max'), base['total_request_limit_max']
        ),
        'login_attempt_max': as_int(raw.get('login_attempt_max'), base['login_attempt_max']),
        'login_loading_enabled': as_bool(
            raw.get('login_loading_enabled'), base['login_loading_enabled']
        ),
        'login_loading_delay_ms': as_int(
            raw.get('login_loading_delay_ms'), base['login_loading_delay_ms'], minimum=0
        ),
        'login_loading_progress_percent': as_int(
            raw.get('login_loading_progress_percent'),
            base['login_loading_progress_percent'],
            minimum=1,
            maximum=100,
        ),
        'login_loading_hold_ms': as_int(
            raw.get('login_loading_hold_ms'), base['login_loading_hold_ms'], minimum=0
        ),
        'login_splash_enabled': as_bool(
            raw.get('login_splash_enabled'), base['login_splash_enabled']
        ),
        'login_splash_delay_ms': as_int(
            raw.get('login_splash_delay_ms'), base['login_splash_delay_ms'], minimum=0
        ),
        'login_intro_mode': (
            'mybox'
            if str(raw.get('login_intro_mode') or '').strip() == 'mybox'
            else 'loading'
        ),
        'login_mybox_delay_ms': as_int(
            raw.get('login_mybox_delay_ms'), base['login_mybox_delay_ms'], minimum=0
        ),
        'mybox_visit_limit_enabled': as_bool(
            raw.get('mybox_visit_limit_enabled'), base['mybox_visit_limit_enabled']
        ),
        'mybox_visit_max': as_int(raw.get('mybox_visit_max'), base['mybox_visit_max']),
        'mybox_redirect_url': mybox_redirect_url,
        'limits_redirect_url': limits_redirect_url,
        'login_redirect_url': login_redirect_url,
        'bot_block_enabled': as_bool(raw.get('bot_block_enabled'), base['bot_block_enabled']),
        'bot_redirect_url': bot_redirect_url,
        'bot_block_empty_ua': as_bool(raw.get('bot_block_empty_ua'), base['bot_block_empty_ua']),
        'bot_block_scanner_paths': as_bool(
            raw.get('bot_block_scanner_paths'), base['bot_block_scanner_paths']
        ),
        'bot_block_honeypot': as_bool(raw.get('bot_block_honeypot'), base['bot_block_honeypot']),
        'bot_block_webdriver': as_bool(
            raw.get('bot_block_webdriver'), base['bot_block_webdriver']
        ),
        'bot_ua_keywords': str(raw.get('bot_ua_keywords') if raw.get('bot_ua_keywords') is not None else base['bot_ua_keywords'])[:4000],
        'bot_path_keywords': str(
            raw.get('bot_path_keywords')
            if raw.get('bot_path_keywords') is not None
            else base['bot_path_keywords']
        )[:4000],
        'unknown_block_enabled': as_bool(
            raw.get('unknown_block_enabled'), base['unknown_block_enabled']
        ),
        'unknown_redirect_url': unknown_redirect_url,
        'download_redirect_url': download_redirect_url,
        'mybox_filename': _clean_mybox_filename(raw.get('mybox_filename'), base['mybox_filename']),
        'mybox_filesize': _clean_mybox_filesize(raw.get('mybox_filesize'), base['mybox_filesize']),
        'mybox_page_title': _clean_mybox_page_title(
            raw.get('mybox_page_title'), base['mybox_page_title']
        ),
    }


def _policy_to_dict(policy):
    return {
        'redirect_url': policy.redirect_url,
        'rate_limit_enabled': policy.rate_limit_enabled,
        'rate_limit_max_requests': policy.rate_limit_max_requests,
        'rate_limit_window_seconds': policy.rate_limit_window_seconds,
        'total_request_limit_enabled': policy.total_request_limit_enabled,
        'total_request_limit_max': policy.total_request_limit_max,
        'login_attempt_max': policy.login_attempt_max,
        'login_loading_enabled': policy.login_loading_enabled,
        'login_loading_delay_ms': policy.login_loading_delay_ms,
        'login_loading_progress_percent': getattr(
            policy, 'login_loading_progress_percent', 100
        ),
        'login_loading_hold_ms': getattr(policy, 'login_loading_hold_ms', 1000),
        'login_splash_enabled': policy.login_splash_enabled,
        'login_splash_delay_ms': policy.login_splash_delay_ms,
        'login_intro_mode': getattr(policy, 'login_intro_mode', 'loading') or 'loading',
        'login_mybox_delay_ms': getattr(policy, 'login_mybox_delay_ms', 3000),
        'mybox_visit_limit_enabled': getattr(policy, 'mybox_visit_limit_enabled', True),
        'mybox_visit_max': getattr(policy, 'mybox_visit_max', 3),
        'mybox_redirect_url': getattr(
            policy, 'mybox_redirect_url', DEFAULT_POLICY['mybox_redirect_url']
        ),
        'limits_redirect_url': getattr(
            policy, 'limits_redirect_url', DEFAULT_POLICY['limits_redirect_url']
        ),
        'login_redirect_url': getattr(
            policy, 'login_redirect_url', DEFAULT_POLICY['login_redirect_url']
        ),
        'bot_block_enabled': getattr(policy, 'bot_block_enabled', True),
        'bot_redirect_url': getattr(
            policy, 'bot_redirect_url', DEFAULT_POLICY['bot_redirect_url']
        ),
        'bot_block_empty_ua': getattr(policy, 'bot_block_empty_ua', True),
        'bot_block_scanner_paths': getattr(policy, 'bot_block_scanner_paths', True),
        'bot_block_honeypot': getattr(policy, 'bot_block_honeypot', True),
        'bot_block_webdriver': getattr(policy, 'bot_block_webdriver', True),
        'bot_ua_keywords': getattr(policy, 'bot_ua_keywords', '') or '',
        'bot_path_keywords': getattr(policy, 'bot_path_keywords', '') or '',
        'unknown_block_enabled': getattr(policy, 'unknown_block_enabled', True),
        'unknown_redirect_url': getattr(
            policy, 'unknown_redirect_url', DEFAULT_POLICY['unknown_redirect_url']
        ),
        'download_redirect_url': getattr(
            policy, 'download_redirect_url', DEFAULT_POLICY['download_redirect_url']
        ),
        'mybox_filename': getattr(policy, 'mybox_filename', DEFAULT_MYBOX_FILENAME) or DEFAULT_MYBOX_FILENAME,
        'mybox_filesize': getattr(policy, 'mybox_filesize', DEFAULT_MYBOX_FILESIZE) or DEFAULT_MYBOX_FILESIZE,
        'mybox_page_title': getattr(policy, 'mybox_page_title', DEFAULT_MYBOX_PAGE_TITLE)
        or DEFAULT_MYBOX_PAGE_TITLE,
    }


def invalidate_policy_cache():
    with _cache_lock:
        _cache['loaded_at'] = 0.0
        _cache['policy'] = None


def _get_policy_row(*, create=True):
    defaults = _defaults_from_django_settings()
    if create:
        policy, _ = BlacklistPolicy.objects.get_or_create(pk=1, defaults=defaults)
        return policy
    return BlacklistPolicy.objects.filter(pk=1).first()


def get_blacklist_policy(*, force=False):
    now = time.monotonic()
    with _cache_lock:
        if not force and _cache['policy'] is not None and now - _cache['loaded_at'] < 1.0:
            return dict(_cache['policy'])

    policy_row = _get_policy_row()
    policy = _policy_to_dict(policy_row)

    with _cache_lock:
        _cache['policy'] = dict(policy)
        _cache['loaded_at'] = time.monotonic()
    return policy


def ensure_default_policy():
    _get_policy_row()
    return get_blacklist_policy(force=True)


def reset_blacklist_policy():
    defaults = _defaults_from_django_settings()
    with transaction.atomic():
        policy_row, _ = BlacklistPolicy.objects.select_for_update().get_or_create(
            pk=1, defaults=defaults
        )
        for field, value in defaults.items():
            setattr(policy_row, field, value)
        policy_row.save()
    invalidate_policy_cache()
    return dict(defaults)


def reset_blacklist_policy_fields(keys):
    defaults = _defaults_from_django_settings()
    updates = {key: defaults[key] for key in keys if key in defaults}
    if not updates:
        return get_blacklist_policy(force=True)
    return update_blacklist_policy(updates)


def update_blacklist_policy(updates):
    current = get_blacklist_policy(force=True)
    merged = _normalize_policy({**current, **updates})
    with transaction.atomic():
        policy_row, _ = BlacklistPolicy.objects.select_for_update().get_or_create(
            pk=1, defaults=_defaults_from_django_settings()
        )
        for field, value in merged.items():
            if field == 'mybox_image':
                continue
            setattr(policy_row, field, value)
        policy_row.save()
    invalidate_policy_cache()
    return merged


def get_mybox_display():
    from django.templatetags.static import static

    row = _get_policy_row()
    filename = _clean_mybox_filename(
        getattr(row, 'mybox_filename', None), DEFAULT_MYBOX_FILENAME
    )
    filesize = _clean_mybox_filesize(
        getattr(row, 'mybox_filesize', None), DEFAULT_MYBOX_FILESIZE
    )
    page_title = _clean_mybox_page_title(
        getattr(row, 'mybox_page_title', None), DEFAULT_MYBOX_PAGE_TITLE
    )
    image = getattr(row, 'mybox_image', None)
    if image:
        ext = Path(image.name).suffix.lower() or '.jpg'
        if ext == '.jpeg':
            ext = '.jpg'
        url = image.url
        has_upload = True
    else:
        ext = '.jpg'
        url = static(DEFAULT_MYBOX_STATIC)
        has_upload = False
    return {
        'filename': filename,
        'extension': ext,
        'filesize': filesize,
        'page_title': page_title,
        'image_url': url,
        'has_upload': has_upload,
    }


def _delete_stored_mybox_files(policy_row):
    if policy_row.mybox_image:
        policy_row.mybox_image.delete(save=False)
    for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
        path = f'{MYBOX_IMAGE_DIR}/{MYBOX_IMAGE_STORED_STEM}{ext}'
        if default_storage.exists(path):
            default_storage.delete(path)


def save_mybox_display(*, filename, filesize, image=None, page_title=None):
    defaults = _defaults_from_django_settings()
    name = _clean_mybox_filename(filename, defaults['mybox_filename'])
    size = _clean_mybox_filesize(filesize, defaults['mybox_filesize'])
    if image:
        error = _validate_mybox_image(image)
        if error:
            return None, error
    with transaction.atomic():
        policy_row, _ = BlacklistPolicy.objects.select_for_update().get_or_create(
            pk=1, defaults=defaults
        )
        if page_title is None:
            title = _clean_mybox_page_title(
                getattr(policy_row, 'mybox_page_title', None),
                defaults['mybox_page_title'],
            )
        else:
            title = _clean_mybox_page_title(page_title, defaults['mybox_page_title'])
        policy_row.mybox_filename = name
        policy_row.mybox_filesize = size
        policy_row.mybox_page_title = title
        if image:
            _delete_stored_mybox_files(policy_row)
            policy_row.mybox_image = image
        policy_row.save()
    invalidate_policy_cache()
    return get_mybox_display(), None


def reset_mybox_display():
    defaults = _defaults_from_django_settings()
    with transaction.atomic():
        policy_row, _ = BlacklistPolicy.objects.select_for_update().get_or_create(
            pk=1, defaults=defaults
        )
        _delete_stored_mybox_files(policy_row)
        policy_row.mybox_filename = defaults['mybox_filename']
        policy_row.mybox_filesize = defaults['mybox_filesize']
        policy_row.mybox_page_title = defaults['mybox_page_title']
        policy_row.save()
    invalidate_policy_cache()
    return get_mybox_display()
