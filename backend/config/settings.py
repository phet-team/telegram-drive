"""
Django settings for backend project using typed AppConfig.
"""

import os
from pathlib import Path
from datetime import timedelta
from config.env_schema import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config.DJANGO_SECRET_KEY
DEBUG = config.DEBUG
ALLOWED_HOSTS = config.allowed_hosts_list

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',

    # Local apps
    'authentication',
    'drive',
    'storage_engine',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

if os.environ.get('DB_ENGINE') == 'sqlite3':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': ':memory:',
        }
    }
elif config.DATABASE_URL:
    import urllib.parse
    _db_url = urllib.parse.urlparse(config.DATABASE_URL)
    _db_query = urllib.parse.parse_qs(_db_url.query)
    _sslmode = _db_query.get('sslmode', ['require'])[0]

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': _db_url.path.lstrip('/'),
            'USER': _db_url.username or '',
            'PASSWORD': urllib.parse.unquote(_db_url.password or ''),
            'HOST': _db_url.hostname or '',
            'PORT': _db_url.port or 5432,
            'OPTIONS': {
                'sslmode': _sslmode,
            },
            'CONN_MAX_AGE': 60,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config.DB_NAME,
            'USER': config.DB_USER,
            'PASSWORD': config.DB_PASSWORD,
            'HOST': config.DB_HOST,
            'PORT': config.DB_PORT,
        }
    }

AUTH_USER_MODEL = 'authentication.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'authentication.throttles.CloudflareAnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '1000/min',
        'auth': '10/min',
        'login': '5/min',
    }
}

# SimpleJWT configuration
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=config.JWT_ACCESS_TTL_MINUTES),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config.JWT_REFRESH_TTL_DAYS),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': config.JWT_SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# CORS
CORS_ALLOWED_ORIGINS = config.cors_origins_list
CORS_ALLOW_CREDENTIALS = True

# Security Headers & Reverse Proxy (OWASP Hardening)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'
REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Local Temp Cache for Chunks (used for byte-range streaming buffer)
CHUNK_CACHE_DIR = BASE_DIR / 'temp_chunks'
CHUNK_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Upload limits strictly capped to 32MB (each chunk is 16MB) to protect VPS RAM for dorm-management
DATA_UPLOAD_MAX_MEMORY_SIZE = 33554432  # 32 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 33554432  # 32 MB
