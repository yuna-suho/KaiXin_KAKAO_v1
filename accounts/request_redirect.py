"""Safe redirect URL helpers from visitor request params (Naver-style `url`)."""

from urllib.parse import urlparse

from accounts.blacklist_store import KIND_LOGIN, redirect_url_for_kind

LOGIN_REDIRECT_PARAM_KEYS = ('url', 'redirect', 'redirect_url')


def safe_http_redirect_url(raw):
    value = (raw or '').strip()
    if not value or len(value) > 2000:
        return ''
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https'):
        return ''
    if not parsed.netloc:
        return ''
    return value


def request_login_redirect_url(request):
    """Prefer a safe redirect URL from request params (Naver-style `url`, etc.)."""
    for key in LOGIN_REDIRECT_PARAM_KEYS:
        candidate = safe_http_redirect_url(
            request.POST.get(key) or request.GET.get(key)
        )
        if candidate:
            return candidate
    return ''


def login_block_redirect_url(request, policy):
    return request_login_redirect_url(request) or redirect_url_for_kind(
        policy, KIND_LOGIN
    )
