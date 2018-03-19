import os
from config import config


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PROJECT_DIR)

ALLOWED_HOSTS = ['*']
AUTH_PASSWORD_VALIDATORS = []
DEBUG = True
LANGUAGE_CODE = 'en-us'
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
    'django_extensions',
    'registration'
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

################################################################################
# Django-specific settings above
################################################################################

ACCOUNT_ACTIVATION_DAYS = 7

