from datetime import datetime, timezone

from django.utils.timezone import is_aware, make_aware


def to_jsonable(value):
    if isinstance(value, datetime):
        if not is_aware(value):
            value = make_aware(value, timezone.utc)
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def parse_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = make_aware(parsed, timezone.utc)
    return parsed
