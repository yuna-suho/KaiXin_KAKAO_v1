import sys

from accounts.models import RequestLog
from accounts.utils import parse_datetime


def insert_request_log(document):
    if not isinstance(document, dict):
        return False

    timestamp = parse_datetime(document.get('timestamp'))
    if timestamp is None:
        return False

    try:
        RequestLog.objects.create(
            timestamp=timestamp,
            method=document.get('method') or '',
            path=document.get('path') or '',
            ip=document.get('ip') or 'unknown',
            device=document.get('device') or '',
            os=document.get('os') or '',
            browser=document.get('browser') or '',
            model=document.get('model') or '',
            language=document.get('language') or '',
            user_agent=document.get('user_agent') or '',
            query=document.get('query') if isinstance(document.get('query'), dict) else {},
            body=document.get('body') if isinstance(document.get('body'), dict) else {},
        )
        return True
    except Exception as exc:
        print(f'[logs] failed to save request log: {exc}', file=sys.stderr)
        return False
