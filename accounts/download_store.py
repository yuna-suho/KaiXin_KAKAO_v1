"""Upload and resolve public download files under /download/<any>/<file>."""

import re
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.urls import reverse

from accounts.models import DownloadFile

_UNSAFE_FILENAME = re.compile(r'[^\w.\- ()\[\]]+', re.UNICODE)
# Shown in admin as a sample middle path; any non-empty path works at request time.
SAMPLE_DOWNLOAD_PATH = 'x'


def download_max_bytes():
    return int(getattr(settings, 'DOWNLOAD_MAX_BYTES', 50 * 1024 * 1024))


def sanitize_download_filename(raw):
    name = Path((raw or '').replace('\\', '/')).name.strip()
    if not name or name in {'.', '..'}:
        return ''
    name = _UNSAFE_FILENAME.sub('_', name).strip(' ._')
    if not name or name in {'.', '..'}:
        return ''
    return name[:200]


def is_usable_download_path(raw):
    """Middle URL path may be anything except empty / traversal."""
    value = (raw or '').strip().strip('/')
    if not value:
        return False
    parts = [p for p in value.replace('\\', '/').split('/') if p]
    if not parts:
        return False
    return all(part not in {'.', '..'} for part in parts)


def format_byte_size(num_bytes):
    try:
        size = int(num_bytes)
    except (TypeError, ValueError):
        size = 0
    if size < 1024:
        return f'{size} B'
    units = ('KB', 'MB', 'GB', 'TB')
    value = float(size)
    for unit in units:
        value /= 1024.0
        if value < 1024 or unit == units[-1]:
            if value >= 100 or unit == 'KB':
                return f'{value:.0f} {unit}'
            return f'{value:.1f} {unit}'
    return f'{size} B'


def public_download_path(filename, any_path=SAMPLE_DOWNLOAD_PATH):
    return reverse(
        'download_file',
        kwargs={'any_path': any_path, 'filename': filename},
    )


def list_download_files():
    rows = []
    for item in DownloadFile.objects.all():
        rows.append(
            {
                'id': str(item.id),
                'filename': item.filename,
                'size': item.size,
                'size_label': format_byte_size(item.size),
                'content_type': item.content_type or '',
                'created_at': item.created_at,
                'path': public_download_path(item.filename),
            }
        )
    return rows


def get_download_file(filename, *, any_path=None):
    if any_path is not None and not is_usable_download_path(any_path):
        return None
    name = sanitize_download_filename(filename)
    if not name:
        return None
    try:
        return DownloadFile.objects.get(filename=name)
    except DownloadFile.DoesNotExist:
        return None


def create_download_file(uploaded, *, filename=None):
    if uploaded is None:
        return None, 'Choose a file to upload.'
    max_bytes = download_max_bytes()
    size = getattr(uploaded, 'size', None)
    if size is None:
        return None, 'Could not read file size.'
    if size <= 0:
        return None, 'Empty files are not allowed.'
    if size > max_bytes:
        return None, f'File is too large (max {format_byte_size(max_bytes)}).'

    name = sanitize_download_filename(filename or getattr(uploaded, 'name', ''))
    if not name:
        return None, 'Invalid file name.'

    content_type = (getattr(uploaded, 'content_type', None) or '').strip()[:255]

    with transaction.atomic():
        if DownloadFile.objects.filter(filename=name).exists():
            return None, 'That file name is already in use.'
        row = DownloadFile(
            filename=name,
            size=size,
            content_type=content_type,
        )
        row.file = uploaded
        row.save()
    return row, None


def delete_download_file(file_id):
    file_id = (file_id or '').strip()
    if not file_id:
        return False
    try:
        row = DownloadFile.objects.get(pk=file_id)
    except (DownloadFile.DoesNotExist, ValueError):
        return False
    storage_key = row.file.name if row.file else ''
    if row.file:
        row.file.delete(save=False)
    storage = row.file.storage
    if storage_key:
        parent = str(Path(storage_key).parent).replace('\\', '/')
        try:
            dirs, files = storage.listdir(parent)
            if not dirs and not files:
                location = getattr(storage, 'location', None)
                if location:
                    path = Path(location) / parent
                    if path.is_dir():
                        path.rmdir()
        except (FileNotFoundError, OSError, NotImplementedError):
            pass
    row.delete()
    return True


def clear_download_files():
    deleted = 0
    for row in DownloadFile.objects.all():
        if delete_download_file(str(row.id)):
            deleted += 1
    return deleted
