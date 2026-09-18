import sys
import uuid
from datetime import datetime, timezone

from django.db import IntegrityError
from django.utils.timezone import is_naive, localtime, make_aware, now as django_now

from accounts.models import RequestLog
from accounts.utils import parse_datetime, to_jsonable
from kaixin.models import AdminUser

_DT_MIN = datetime.min.replace(tzinfo=timezone.utc)
_DT_MAX = datetime.max.replace(tzinfo=timezone.utc)


def _admin_to_dict(admin):
    return {
        '_id': str(admin.pk),
        'username': admin.username,
        'password_hash': admin.password_hash,
        'is_superadmin': admin.is_superadmin,
        'is_approved': admin.is_approved,
        'created_at': admin.created_at,
    }


def _log_to_dict(log):
    return {
        'timestamp': log.timestamp,
        'method': log.method,
        'path': log.path,
        'ip': log.ip,
        'device': log.device,
        'os': log.os,
        'browser': log.browser,
        'model': log.model,
        'language': log.language,
        'user_agent': log.user_agent,
        'query': log.query,
        'body': log.body,
    }


def count_admin_users():
    return AdminUser.objects.count()


def create_admin_user(username, password_hash, *, is_superadmin, is_approved):
    username = (username or '').strip()
    if not username:
        return None

    try:
        admin = AdminUser.objects.create(
            username=username,
            password_hash=password_hash,
            is_superadmin=bool(is_superadmin),
            is_approved=bool(is_approved),
            created_at=django_now(),
        )
    except IntegrityError:
        return None
    return _admin_to_dict(admin)


def find_admin_by_username(username):
    username = (username or '').strip()
    if not username:
        return None
    admin = AdminUser.objects.filter(username=username).first()
    return _admin_to_dict(admin) if admin else None


def find_admin_by_id(admin_id):
    admin_id = (admin_id or '').strip()
    if not admin_id:
        return None
    try:
        admin_uuid = uuid.UUID(admin_id)
    except ValueError:
        return None
    admin = AdminUser.objects.filter(pk=admin_uuid).first()
    return _admin_to_dict(admin) if admin else None


def list_pending_admins():
    return [
        _admin_to_dict(admin)
        for admin in AdminUser.objects.filter(is_approved=False).order_by('created_at')
    ]


def list_admin_users():
    return [_admin_to_dict(admin) for admin in AdminUser.objects.order_by('created_at')]


def set_admin_approval(admin_id, approved):
    admin_id = (admin_id or '').strip()
    if not admin_id:
        return None
    try:
        admin_uuid = uuid.UUID(admin_id)
    except ValueError:
        return None

    admin = AdminUser.objects.filter(pk=admin_uuid).first()
    if admin is None or admin.is_superadmin:
        return None

    admin.is_approved = bool(approved)
    admin.save(update_fields=['is_approved'])
    return _admin_to_dict(admin)


def delete_admin_user(admin_id):
    admin_id = (admin_id or '').strip()
    if not admin_id:
        return False
    try:
        admin_uuid = uuid.UUID(admin_id)
    except ValueError:
        return False

    deleted, _ = AdminUser.objects.filter(pk=admin_uuid, is_superadmin=False).delete()
    return bool(deleted)


def _log_timestamp(doc):
    return parse_datetime(doc.get('timestamp')) or _DT_MIN


def _body_id(doc):
    body = doc.get('body')
    if isinstance(body, dict):
        return body.get('id')
    return None


def aggregate_logs_by_ip():
    groups = {}
    try:
        for log in RequestLog.objects.iterator():
            doc = _log_to_dict(log)
            ip = doc.get('ip') or 'unknown'
            ts = _log_timestamp(doc)
            bucket = groups.get(ip)
            if bucket is None:
                groups[ip] = {
                    '_id': ip,
                    'count': 1,
                    'last_seen': ts,
                    'first_seen': ts,
                    'latest_method': doc.get('method'),
                    'latest_path': doc.get('path'),
                    'latest_id': _body_id(doc),
                    'devices': {doc.get('device')} if doc.get('device') else set(),
                    'oses': {doc.get('os')} if doc.get('os') else set(),
                }
                continue
            bucket['count'] += 1
            if ts >= (bucket['last_seen'] or _DT_MIN):
                bucket['last_seen'] = ts
                bucket['latest_method'] = doc.get('method')
                bucket['latest_path'] = doc.get('path')
                bucket['latest_id'] = _body_id(doc)
            if ts <= (bucket['first_seen'] or _DT_MAX):
                bucket['first_seen'] = ts
            if doc.get('device'):
                bucket['devices'].add(doc.get('device'))
            if doc.get('os'):
                bucket['oses'].add(doc.get('os'))
    except Exception as exc:
        print(f'[kaixin.store] failed to aggregate logs: {exc}', file=sys.stderr)
        return []

    rows = []
    for bucket in groups.values():
        rows.append(
            {
                **bucket,
                'devices': sorted(value for value in bucket['devices'] if value),
                'oses': sorted(value for value in bucket['oses'] if value),
            }
        )
    rows.sort(key=lambda item: item.get('last_seen') or _DT_MIN, reverse=True)
    return rows


def list_methods_for_ip(ip):
    # Clear model Meta.ordering first: SQLite DISTINCT is ineffective when
    # ORDER BY timestamp is still applied, which duplicates method chips.
    methods = (
        RequestLog.objects.filter(ip=ip)
        .exclude(method='')
        .order_by()
        .values_list('method', flat=True)
        .distinct()
    )
    return sorted({str(method) for method in methods if method})


def list_logs_for_ip(ip, limit=500, method=None):
    queryset = RequestLog.objects.filter(ip=ip)
    if method:
        queryset = queryset.filter(method=method)
    logs = [_log_to_dict(log) for log in queryset.order_by('-timestamp')[:limit]]
    return logs


def serialize_log_document(document):
    return {key: to_jsonable(value) for key, value in document.items()}


def export_request_logs(*, ip=None, method=None, since=None, until=None, limit=100000):
    since_dt = parse_datetime(since) if since is not None else None
    until_dt = parse_datetime(until) if until is not None else None

    queryset = RequestLog.objects.all()
    if ip:
        queryset = queryset.filter(ip=ip)
    if method:
        queryset = queryset.filter(method=method)
    if since_dt is not None:
        queryset = queryset.filter(timestamp__gte=since_dt)
    if until_dt is not None:
        queryset = queryset.filter(timestamp__lte=until_dt)

    matched = [_log_to_dict(log) for log in queryset.order_by('-timestamp')[:limit]]
    return [serialize_log_document(doc) for doc in matched]


def delete_logs_for_ips(ips):
    cleaned = []
    seen = set()
    for ip in ips or []:
        value = (ip or '').strip()
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    if not cleaned:
        return 0
    deleted, _ = RequestLog.objects.filter(ip__in=cleaned).delete()
    return deleted


def delete_logs_for_ip(ip):
    return delete_logs_for_ips([ip])


def delete_all_logs():
    deleted, _ = RequestLog.objects.all().delete()
    return deleted


def format_timestamp(value):
    parsed = parse_datetime(value) if not isinstance(value, datetime) else value
    if isinstance(parsed, datetime):
        if is_naive(parsed):
            parsed = make_aware(parsed, timezone.utc)
        return localtime(parsed).strftime('%Y-%m-%d %H:%M:%S')
    return str(value) if value else '-'


def format_request_data(data):
    if not data:
        return '-'
    if not isinstance(data, dict):
        return str(data)
    lines = []
    for key in sorted(data.keys(), key=lambda item: str(item)):
        value = data[key]
        if isinstance(value, list):
            rendered = ', '.join(str(item) for item in value)
        else:
            rendered = str(value)
        lines.append(f'{key}={rendered}')
    return '\n'.join(lines) if lines else '-'
