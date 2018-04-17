import os
import sys
from config import config


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PROJECT_DIR)

sys.path.append(PROJECT_DIR)
ALLOWED_HOSTS = ['*']
AUTH_PASSWORD_VALIDATORS = []
DEBUG = True
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = os.path.join(BASE_DIR, 'emails')
LANGUAGE_CODE = 'en-us'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
ROOT_URLCONF = 'concordia.urls'
SECRET_KEY = config('DJANGO', 'SECRET_KEY', 'super-secret-key')
STATIC_ROOT = 'static'
STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(PROJECT_DIR, 'static'),\
 os.path.join('/'.join(PROJECT_DIR.split('/')[:-1]), 'transcribr/transcribr/static')]
TEMPLATE_DEBUG = False
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True
WSGI_APPLICATION = 'concordia.wsgi.application'

ADMIN_SITE = {
    'site_header': config('DJANGO', 'ADMIN_SITE_HEADER', 'Concordia Admin'),
    'site_title': config('DJANGO', 'ADMIN_SITE_TITLE', 'Concordia'),
}

DATABASES = {
    'default': {
        'ENGINE': config('DJANGO', 'DB_ENGINE', 'django.db.backends.postgresql_psycopg2'),
        'NAME': config('DJANGO', 'DB_NAME', 'concordia'),
        'USER': config('DJANGO', 'DB_USER', 'concordia'),
        'PASSWORD': config('DJANGO', 'DB_PASSWORD', 'concordia'),
        'HOST': '0.0.0.0',  # config('DJANGO', 'DB_HOST', '127.0.0.1'),
        'PORT': 5432  # config('DJANGO', 'DB_PORT', 5432),
    }
}

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'transcribr',
    'importer',
    'concordia',
    'concordia.experiments.wireframes',
]

if DEBUG:
    INSTALLED_APPS += ['django_extensions', ]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [os.path.join(PROJECT_DIR, 'templates'), ],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
        ],
    },
}]


# Celery settings
CELERY_BROKER_URL = config('CELERY', 'BROKER_URL', 'pyamqp://rabbit@rabbit//')
CELERY_RESULT_BACKEND = config('CELERY', 'RESULT_BACKEND', 'rpc://')

CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_IMPORTS = ('importer.importer.tasks',)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'long': {
            'format': '[{asctime} {levelname} {name}:{lineno}] {message}',
            'datefmt': '%Y-%m-%dT%H:%M:%S',
            'style': '{'
        },
        'short': {
            'format': '[{levelname} {name}] {message}',
            'datefmt': '%Y-%m-%dT%H:%M:%S',
            'style': '{'
        },
    },
    'handlers': {
        'stream': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'long',
        },
        'null': {
            'level': 'DEBUG',
            'class': 'logging.NullHandler',
        },
        'file': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'long',
            'filename': '{}/logs/concordia.log'.format(BASE_DIR),
            'when': 'H',
            'interval': 3,
            'backupCount': 16
        }
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'stream'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },

}


################################################################################
# Django-specific settings above
################################################################################

ACCOUNT_ACTIVATION_DAYS = 7

REGISTRATION_URLS = config(
    'DJANGO',
    'REGISTRATION_URLS',
    'registration.backends.simple.urls'
)


REST_FRAMEWORK = {
    'PAGE_SIZE': config('DJRF', 'PAGE_SIZE', 10, int),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
}

# TRANSCRIBR = dict(
#     netloc=config('TRANSCRIBR', 'NETLOC', 'http://0.0.0.0:8000'),
# )

TRANSCRIBR = dict(
    netloc='http://0.0.0.0:8000'
)
