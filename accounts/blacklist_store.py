import ipaddress
import re
import threading
import time
import uuid

from django.db import IntegrityError
from django.db.models import F
from django.utils.timezone import now as django_now

from accounts.models import (
    KIND_BOT,
    KIND_LIMIT,
    KIND_LOGIN,
    KIND_MANUAL,
    KIND_MYBOX,
    KIND_RATE,
    KIND_UNKNOWN,
    BlacklistEntry,
    LoginAttemptCounter,
    MyboxVisitCounter,
)

GLOBAL_BLOCK_KINDS = (KIND_MANUAL, KIND_LOGIN, KIND_BOT, KIND_UNKNOWN, KIND_RATE, KIND_LIMIT)
ALL_KINDS = GLOBAL_BLOCK_KINDS + (KIND_MYBOX,)

KIND_LABELS = {
    KIND_MANUAL: 'Manual',
    KIND_RATE: 'Rate limit',
    KIND_LOGIN: 'Login attempts',
    KIND_LIMIT: 'Total requests',
    KIND_MYBOX: 'MYBOX visits',
    KIND_BOT: 'Bot',
    KIND_UNKNOWN: 'Unknown',
}

KIND_REDIRECT_KEYS = {
    KIND_MANUAL: 'redirect_url',
    KIND_LOGIN: 'login_redirect_url',
    KIND_BOT: 'bot_redirect_url',
    KIND_UNKNOWN: 'unknown_redirect_url',
    KIND_RATE: 'limits_redirect_url',
    KIND_LIMIT: 'limits_redirect_url',
    KIND_MYBOX: 'mybox_redirect_url',
}

_FALLBACK_REDIRECT = 'https://www.naver.com/'

LOCAL_IPS = frozenset({'127.0.0.1', '::1', 'localhost'})
_IPV4_WITH_PORT = re.compile(r'^(\d{1,3}(?:\.\d{1,3}){3}):\d+$')

_cache_lock = threading.Lock()
_cache = {'loaded_at': 0.0, 'by_kind': {}, 'all': frozenset()}


def _entry_to_dict(entry):
    return {
        '_id': str(entry.pk),
        'ip': entry.ip,
        'kind': entry.kind,
        'note': entry.note,
        'created_at': entry.created_at,
    }


def _parse_ip(value):
    text = (value or '').strip()
    if not text or text.lower() == 'unknown':
        return ''
    if text.startswith('[') and ']' in text:
        text = text[1:text.index(']')]
    else:
        match = _IPV4_WITH_PORT.match(text)
        if match:
            text = match.group(1)
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        lowered = text.lower()
        if lowered in LOCAL_IPS:
            return '127.0.0.1' if lowered != '::1' else '::1'
        return ''


def is_local_ip(ip):
    value = (ip or '').strip().lower()
    if not value:
        return False
    if value in LOCAL_IPS:
        return True
    parsed = _parse_ip(value)
    if not parsed:
        return False
    try:
        addr = ipaddress.ip_address(parsed)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    mapped = getattr(addr, 'ipv4_mapped', None)
    return bool(mapped is not None and mapped.is_loopback)


def _is_proxy_peer(ip):
    """True when REMOTE_ADDR is the reverse proxy, not the visitor."""
    if not ip or is_local_ip(ip):
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return bool(addr.is_private or addr.is_link_local)


def _forwarded_ips(request):
    ips = []

    def add(raw, reverse=False):
        if not raw:
            return
        parts = [part.strip() for part in str(raw).split(',') if part.strip()]
        if reverse:
            parts.reverse()
        for part in parts:
            parsed = _parse_ip(part)
            if parsed:
                ips.append(parsed)

    add(request.META.get('HTTP_CF_CONNECTING_IP'))
    add(request.META.get('HTTP_X_REAL_IP'))
    add(request.META.get('HTTP_X_FORWARDED_FOR'), reverse=True)
    return ips


def get_client_ip(request):
    """Resolve the visitor IP behind nginx/Cloudflare on localhost."""
    remote = _parse_ip(request.META.get('REMOTE_ADDR'))
    forwarded = _forwarded_ips(request)

    if remote and not _is_proxy_peer(remote):
        return remote

    for ip in forwarded:
        if not is_local_ip(ip):
            return ip
    if remote:
        return remote
    if forwarded:
        return forwarded[0]
    return 'unknown'


def _increment_ip_counter(model, ip):
    ip = (ip or '').strip()
    if not ip:
        return 0

    updated = model.objects.filter(ip=ip).update(count=F('count') + 1)
    if not updated:
        try:
            model.objects.create(ip=ip, count=1)
            return 1
        except IntegrityError:
            model.objects.filter(ip=ip).update(count=F('count') + 1)

    count = model.objects.filter(ip=ip).values_list('count', flat=True).first()
    return int(count or 0)


def increment_login_attempt_count(ip, max_attempts=None):
    """Atomically count a login POST. Shared across gunicorn workers via SQLite."""
    return _increment_ip_counter(LoginAttemptCounter, ip)


def reset_login_attempt_count(ip):
    ip = (ip or '').strip()
    if not ip:
        return 0
    deleted, _ = LoginAttemptCounter.objects.filter(ip=ip).delete()
    return deleted


def increment_mybox_visit_count(ip, max_visits=None):
    """Atomically count a /mybox/ visit. Shared across gunicorn workers via SQLite."""
    return _increment_ip_counter(MyboxVisitCounter, ip)


def reset_mybox_visit_count(ip):
    ip = (ip or '').strip()
    if not ip:
        return 0
    deleted, _ = MyboxVisitCounter.objects.filter(ip=ip).delete()
    return deleted


def list_mybox_visit_counts():
    blocked = get_ips_for_kind(KIND_MYBOX)
    return [
        {
            'ip': row.ip,
            'count': int(row.count),
            'updated_at': row.updated_at,
            'blocked': row.ip in blocked,
        }
        for row in MyboxVisitCounter.objects.order_by('-updated_at', 'ip')
    ]


def _clear_request_limit_state(ip, kind=None):
    if kind not in (None, KIND_RATE, KIND_LIMIT):
        return
    from accounts import middleware as mw

    if kind in (None, KIND_RATE):
        mw._rate_buckets.pop(ip, None)
    if kind in (None, KIND_LIMIT):
        mw._total_request_counts.pop(ip, None)


def _invalidate_lookup_cache():
    with _cache_lock:
        _cache['loaded_at'] = 0.0


def _load_cache(force=False):
    now = time.monotonic()
    with _cache_lock:
        if not force and _cache['loaded_at'] and now - _cache['loaded_at'] < 1.0:
            return _cache

    by_kind = {kind: set() for kind in ALL_KINDS}
    all_ips = set()
    for entry in BlacklistEntry.objects.only('ip', 'kind').iterator():
        by_kind.setdefault(entry.kind, set()).add(entry.ip)
        all_ips.add(entry.ip)

    with _cache_lock:
        _cache['by_kind'] = {k: frozenset(v) for k, v in by_kind.items()}
        _cache['all'] = frozenset(all_ips)
        _cache['loaded_at'] = time.monotonic()
        return _cache


def get_ips_for_kind(kind):
    cache = _load_cache()
    return cache['by_kind'].get(kind, frozenset())


def is_ip_blocked(ip):
    return primary_block_kind(ip) is not None


def primary_block_kind(ip):
    cache = _load_cache()
    ip = (ip or '').strip()
    if not ip:
        return None
    for kind in GLOBAL_BLOCK_KINDS:
        if ip in cache['by_kind'].get(kind, frozenset()):
            return kind
    return None


def redirect_url_for_kind(policy, kind):
    key = KIND_REDIRECT_KEYS.get(kind, 'redirect_url')
    url = str((policy or {}).get(key) or (policy or {}).get('redirect_url') or '').strip()
    return url or _FALLBACK_REDIRECT


def redirect_url_for_ip(policy, ip):
    ip = (ip or '').strip()
    for kind in (KIND_MANUAL, KIND_LOGIN, KIND_BOT, KIND_UNKNOWN, KIND_RATE, KIND_LIMIT):
        if ip in get_ips_for_kind(kind):
            return redirect_url_for_kind(policy, kind)
    return redirect_url_for_kind(policy, KIND_MANUAL)


def get_block_reasons(ip):
    ip = (ip or '').strip()
    if not ip:
        return []
    cache = _load_cache()
    reasons = []
    for kind in ALL_KINDS:
        if ip in cache['by_kind'].get(kind, frozenset()):
            reasons.append(KIND_LABELS.get(kind, kind))
    return reasons


def get_block_reasons_map():
    cache = _load_cache()
    result = {}
    for kind in ALL_KINDS:
        label = KIND_LABELS.get(kind, kind)
        for blocked_ip in cache['by_kind'].get(kind, frozenset()):
            result.setdefault(blocked_ip, []).append(label)
    return result


def add_blacklist_ip(ip, kind, note='', *, invalidate=True):
    ip = (ip or '').strip()
    if not ip or kind not in ALL_KINDS or is_local_ip(ip):
        return False

    try:
        BlacklistEntry.objects.create(
            ip=ip,
            kind=kind,
            note=note or '',
            created_at=django_now(),
        )
    except IntegrityError:
        return False

    if invalidate:
        _invalidate_lookup_cache()
    return True


def remove_blacklist_entry(entry_id):
    entry_id = (entry_id or '').strip()
    if not entry_id:
        return False

    try:
        entry_uuid = uuid.UUID(entry_id)
    except ValueError:
        return False

    entry = BlacklistEntry.objects.filter(pk=entry_uuid).first()
    if entry is None:
        return False

    ip = entry.ip
    kind = entry.kind
    entry.delete()
    _invalidate_lookup_cache()
    if kind == KIND_LOGIN:
        reset_login_attempt_count(ip)
    elif kind == KIND_MYBOX:
        reset_mybox_visit_count(ip)
    _clear_request_limit_state(ip, kind)
    return True


def remove_blacklist_ip(ip, kind=None):
    ip = (ip or '').strip()
    if not ip:
        return 0

    queryset = BlacklistEntry.objects.filter(ip=ip)
    if kind in ALL_KINDS:
        queryset = queryset.filter(kind=kind)
    deleted, _ = queryset.delete()
    if deleted:
        _invalidate_lookup_cache()
        if kind in (None, KIND_LOGIN):
            reset_login_attempt_count(ip)
        if kind in (None, KIND_MYBOX):
            reset_mybox_visit_count(ip)
        _clear_request_limit_state(ip, kind)
    return deleted


def clear_blacklist_entries():
    login_ips = list(
        BlacklistEntry.objects.filter(kind=KIND_LOGIN).values_list('ip', flat=True)
    )
    mybox_ips = list(
        BlacklistEntry.objects.filter(kind=KIND_MYBOX).values_list('ip', flat=True)
    )
    rate_ips = list(
        BlacklistEntry.objects.filter(kind=KIND_RATE).values_list('ip', flat=True)
    )
    limit_ips = list(
        BlacklistEntry.objects.filter(kind=KIND_LIMIT).values_list('ip', flat=True)
    )
    deleted, _ = BlacklistEntry.objects.all().delete()
    _invalidate_lookup_cache()
    for ip in login_ips:
        reset_login_attempt_count(ip)
    for ip in mybox_ips:
        reset_mybox_visit_count(ip)
    for ip in rate_ips:
        _clear_request_limit_state(ip, KIND_RATE)
    for ip in limit_ips:
        _clear_request_limit_state(ip, KIND_LIMIT)
    return deleted


def clear_blacklist_entries_for_kind(kind):
    if kind not in ALL_KINDS:
        return 0
    listed = list(BlacklistEntry.objects.filter(kind=kind).values_list('ip', flat=True))
    if not listed:
        return 0
    deleted, _ = BlacklistEntry.objects.filter(kind=kind).delete()
    _invalidate_lookup_cache()
    for ip in listed:
        if kind == KIND_LOGIN:
            reset_login_attempt_count(ip)
        elif kind == KIND_MYBOX:
            reset_mybox_visit_count(ip)
        _clear_request_limit_state(ip, kind)
    return deleted


def delete_mybox_visit_record(ip):
    ip = (ip or '').strip()
    if not ip:
        return False
    listed = remove_blacklist_ip(ip, KIND_MYBOX)
    reset = reset_mybox_visit_count(ip)
    return bool(listed or reset)


def clear_mybox_visit_records():
    mybox_listed = list(
        BlacklistEntry.objects.filter(kind=KIND_MYBOX).values_list('ip', flat=True)
    )
    if mybox_listed:
        BlacklistEntry.objects.filter(kind=KIND_MYBOX).delete()
        _invalidate_lookup_cache()
    deleted, _ = MyboxVisitCounter.objects.all().delete()
    return deleted


def list_blacklist_entries(kind=None):
    queryset = BlacklistEntry.objects.all()
    if kind in ALL_KINDS:
        queryset = queryset.filter(kind=kind)
    return [_entry_to_dict(entry) for entry in queryset]
