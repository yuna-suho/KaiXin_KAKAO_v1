import threading
import time

from django.shortcuts import redirect

from accounts.blacklist_store import (
    KIND_BOT,
    KIND_LIMIT,
    KIND_LOGIN,
    KIND_MYBOX,
    KIND_RATE,
    add_blacklist_ip,
    get_client_ip,
    get_ips_for_kind,
    increment_login_attempt_count,
    increment_mybox_visit_count,
    is_ip_blocked,
    is_local_ip,
    primary_block_kind,
    redirect_url_for_ip,
    redirect_url_for_kind,
)
from accounts.bot_detect import (
    is_bot_user_agent,
    is_scanner_path,
    is_trap_path,
    path_contains_keyword,
    should_trap_path,
)
from accounts.policy_store import get_blacklist_policy
from accounts.request_redirect import request_login_redirect_url

_rate_lock = threading.Lock()
_total_lock = threading.Lock()
_rate_buckets = {}
_total_request_counts = {}


def _add_ip_to_rate_blacklist(client_ip):
    if is_local_ip(client_ip) or client_ip in get_ips_for_kind(KIND_RATE):
        return
    add_blacklist_ip(client_ip, KIND_RATE, note='auto: rate limit')


def _add_ip_to_login_blacklist(client_ip):
    if is_local_ip(client_ip):
        return False
    if client_ip in get_ips_for_kind(KIND_LOGIN):
        return True
    return add_blacklist_ip(client_ip, KIND_LOGIN, note='auto: login attempts')


def _add_ip_to_limit_blacklist(client_ip):
    if is_local_ip(client_ip) or client_ip in get_ips_for_kind(KIND_LIMIT):
        return
    add_blacklist_ip(client_ip, KIND_LIMIT, note='auto: total request limit')


def _add_ip_to_bot_blacklist(client_ip, note='auto: bot'):
    if is_local_ip(client_ip):
        return False
    if client_ip in get_ips_for_kind(KIND_BOT):
        return True
    return add_blacklist_ip(client_ip, KIND_BOT, note=note)


def flag_bot(client_ip, note='auto: bot', *, reason='ua', path='', user_agent=''):
    if is_local_ip(client_ip):
        return False
    return bool(_add_ip_to_bot_blacklist(client_ip, note=note))


def _add_ip_to_mybox_blacklist(client_ip):
    if is_local_ip(client_ip) or client_ip in get_ips_for_kind(KIND_MYBOX):
        return
    add_blacklist_ip(client_ip, KIND_MYBOX, note='auto: mybox visits')


def _is_mybox_path(path):
    return path == '/mybox' or path.startswith('/mybox/')


def _is_mybox_asset_path(path):
    return path.startswith('/static/mybox/') or path.startswith('/media/mybox/')


def _is_login_intro_mybox_path(path):
    return path == '/login-intro-mybox' or path.startswith('/login-intro-mybox/')


def _is_mybox_visit_path(path):
    if _is_login_intro_mybox_path(path):
        return False
    return path.startswith('/mybox/')


def record_login_attempt(client_ip, *, path='', user_agent=''):
    """Count login attempts per IP. After login_attempt_max, blacklist and return True."""
    if is_local_ip(client_ip):
        return False
    policy = get_blacklist_policy()
    max_attempts = policy['login_attempt_max']
    count = increment_login_attempt_count(client_ip, max_attempts)
    blocked = count >= max_attempts
    if blocked:
        _add_ip_to_login_blacklist(client_ip)
    return blocked


def _rate_limit_exceeded(client_ip, policy):
    if is_local_ip(client_ip):
        return False

    max_requests = policy['rate_limit_max_requests']
    window_seconds = policy['rate_limit_window_seconds']
    now = time.monotonic()

    with _rate_lock:
        bucket = _rate_buckets.get(client_ip)
        if bucket is None or now - bucket['start'] >= window_seconds:
            _rate_buckets[client_ip] = {'count': 1, 'start': now}
            return False

        bucket['count'] += 1
        return bucket['count'] > max_requests


def _total_request_limit_exceeded(client_ip, policy):
    if is_local_ip(client_ip):
        return False

    max_requests = policy['total_request_limit_max']

    with _total_lock:
        count = _total_request_counts.get(client_ip, 0)

        if count > max_requests and client_ip not in get_ips_for_kind(KIND_LIMIT):
            count = 0

        count += 1
        _total_request_counts[client_ip] = count
        return count > max_requests


def _mybox_visit_limit_exceeded(client_ip, policy):
    if is_local_ip(client_ip):
        return False, 0

    max_visits = policy['mybox_visit_max']
    count = increment_mybox_visit_count(client_ip, max_visits)
    return count >= max_visits, count


class BlacklistIPMiddleware:
    """Block blacklisted IPs; auto-list using admin-configurable policy."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if (
            path.startswith('/20020522/judy')
            or path.startswith('/20100514/yuna')
            or path.startswith('/kaixin-judy-yuna')
            or path == '/robots.txt'
            or path == '/download'
            or path.startswith('/download/')
        ):
            return self.get_response(request)

        client_ip = get_client_ip(request)
        if is_local_ip(client_ip):
            return self.get_response(request)

        policy = get_blacklist_policy()
        ua = request.META.get('HTTP_USER_AGENT') or ''

        if policy.get('bot_block_enabled'):
            already_bot = client_ip in get_ips_for_kind(KIND_BOT)
            if already_bot or is_bot_user_agent(ua, policy) or should_trap_path(path, policy):
                if not already_bot:
                    if (
                        is_trap_path(path)
                        or is_scanner_path(path)
                        or path_contains_keyword(path, policy)
                    ):
                        note = 'auto: bot path'
                    else:
                        note = 'auto: bot ua'
                    _add_ip_to_bot_blacklist(client_ip, note=note)
                return redirect(redirect_url_for_kind(policy, KIND_BOT))

        if _is_login_intro_mybox_path(path):
            return self.get_response(request)

        # MYBOX is isolated from other blacklist kinds. Applying the global
        # redirect here loops when redirect_url points at /mybox/.
        if _is_mybox_path(path) or _is_mybox_asset_path(path):
            if _is_mybox_visit_path(path):
                already_listed = client_ip in get_ips_for_kind(KIND_MYBOX)
                if policy['mybox_visit_limit_enabled'] and already_listed:
                    return redirect(redirect_url_for_kind(policy, KIND_MYBOX))
                exceeded, _count = _mybox_visit_limit_exceeded(client_ip, policy)
                if policy['mybox_visit_limit_enabled'] and exceeded:
                    _add_ip_to_mybox_blacklist(client_ip)
                    return redirect(redirect_url_for_kind(policy, KIND_MYBOX))
            return self.get_response(request)

        if is_ip_blocked(client_ip):
            target = redirect_url_for_ip(policy, client_ip)
            if primary_block_kind(client_ip) == KIND_LOGIN:
                target = request_login_redirect_url(request) or target
            return redirect(target)

        if policy['rate_limit_enabled']:
            if _rate_limit_exceeded(client_ip, policy):
                _add_ip_to_rate_blacklist(client_ip)
                return redirect(redirect_url_for_kind(policy, KIND_RATE))

        if policy['total_request_limit_enabled']:
            if _total_request_limit_exceeded(client_ip, policy):
                _add_ip_to_limit_blacklist(client_ip)
                return redirect(redirect_url_for_kind(policy, KIND_LIMIT))

        return self.get_response(request)
