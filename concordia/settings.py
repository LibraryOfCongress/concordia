import os
from config import config

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PROJECT_DIR)

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
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True
WSGI_APPLICATION = 'concordia.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': config('DJANGO', 'DB_ENGINE', 'django.db.backends.postgresql_psycopg2'),
        'NAME': config('DJANGO', 'DB_NAME', 'postgres'),
        'USER': config('DJANGO', 'DB_USER', 'postgres'),
        'PASSWORD': config('DJANGO', 'DB_PASSWORD', ''),
        'HOST': config('DJANGO', 'DB_HOST', 'db'),
        'PORT': config('DJANGO', 'DB_PORT', 5432),
    }
}

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'concordia.experiments.wireframes',
    'concordia.experiments.transcribr',
    'concordia.experiments.importer',
    'django_extensions',
]


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
    'DIRS': [os.path.join(PROJECT_DIR, 'templates'),],
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
CELERY_IMPORTS = ('concordia.experiments.importer.tasks',)


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': 'concordia-debug.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}

################################################################################
# Django-specific settings above
################################################################################

ACCOUNT_ACTIVATION_DAYS = 7

