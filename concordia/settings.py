# TODO: use correct copyright header
import os
import sys
from config import config
from machina import get_apps as get_machina_apps
from machina import MACHINA_MAIN_TEMPLATE_DIR
from machina import MACHINA_MAIN_STATIC_DIR

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PROJECT_DIR)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('DJANGO', 'SECRET_KEY')

# Optional SMTP authentication information for EMAIL_HOST.
EMAIL_HOST_USER = ''
EMAIL_HOST_PASSWORD = ''
EMAIL_USE_TLS = False
DEFAULT_FROM_EMAIL = "noreply@loc.gov"

ALLOWED_HOSTS = ['*']

# TODO: production we can not have DEBUG = True
DEBUG = True
# TODO: when running in https change the below value to True
CSRF_COOKIE_SECURE = False


sys.path.append(PROJECT_DIR)
AUTH_PASSWORD_VALIDATORS = []
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
# EMAIL_FILE_PATH = os.path.join(BASE_DIR, 'emails')
EMAIL_HOST = 'localhost'
EMAIL_PORT = 25
LANGUAGE_CODE = 'en-us'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
ROOT_URLCONF = 'concordia.urls'
STATIC_ROOT = 'static'
STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(PROJECT_DIR, 'static'),
                    os.path.join('/'.join(PROJECT_DIR.split('/')[:-1]), 'concordia/static')]
STATICFILES_DIRS = [os.path.join(PROJECT_DIR, 'static'), MACHINA_MAIN_STATIC_DIR]
TEMPLATE_DEBUG = False
TIME_ZONE = 'UTC'
USE_I18N = True
USE_L10N = True
USE_TZ = True
WSGI_APPLICATION = 'concordia.wsgi.application'

ADMIN_SITE = {
    'site_header': config('DJANGO', 'ADMIN_SITE_HEADER'),
    'site_title': config('DJANGO', 'ADMIN_SITE_TITLE'),
}

DATABASES = {
    'default': {
        'ENGINE':   config('DJANGO', 'DB_ENGINE'),
        'NAME':     config('DJANGO', 'DB_NAME'),
        'USER':     config('DJANGO', 'DB_USER'),
        'PASSWORD': config('DJANGO', 'DB_PASSWORD'),
        'HOST':     config('DJANGO', 'DB_HOST'),
        'PORT':     config('DJANGO', 'DB_PORT')
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

    'concordia',
    'exporter',
    'faq',
    'importer',

    'concordia.experiments.wireframes',
 # Machina related apps:
    'mptt',
    'haystack',
    'widget_tweaks',
] + get_machina_apps()


if DEBUG:
    INSTALLED_APPS += ['django_extensions', ]
    INSTALLED_APPS += ['kombu.transport', ]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Machina
    'machina.apps.forum_permission.middleware.ForumPermissionMiddleware',
]

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [os.path.join(PROJECT_DIR, 'templates'), MACHINA_MAIN_TEMPLATE_DIR],
#    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'django.template.context_processors.media',
            # Machina
            'machina.core.context_processors.metadata',
        ],
            'loaders': [
                'django.template.loaders.filesystem.Loader',
                'django.template.loaders.app_directories.Loader',
            ]
    },
}]

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    },
    'machina_attachments': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': '/tmp',
    },
}

HAYSTACK_CONNECTIONS = {
    'default': {
        'ENGINE': 'haystack.backends.whoosh_backend.WhooshEngine',
        'PATH': os.path.join(os.path.dirname(__file__), 'whoosh_index'),
    },
}

CELERY_BROKER_URL = config('CELERY', 'BROKER_URL')
CELERY_RESULT_BACKEND = config('CELERY', 'RESULT_BACKEND')

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
        },
        'celery': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '{}/logs/celery.log'.format(BASE_DIR),
            'formatter': 'long',
            'maxBytes': 1024 * 1024 * 100,  # 100 mb
        }
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'stream'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'celery': {
            'handlers': ['celery', 'stream'],
            'level': 'DEBUG',
        }
    },

}


################################################################################
# Django-specific settings above
################################################################################

ACCOUNT_ACTIVATION_DAYS = 7

REST_FRAMEWORK = {
    'PAGE_SIZE': config('DJRF', 'PAGE_SIZE'),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
}

CONCORDIA = dict(
     netloc=config('CONCORDIA', 'NETLOC'),
)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


LOGIN_URL='/account/login/'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
    {
        'NAME': 'concordia.validators.complexity'
    }
]

