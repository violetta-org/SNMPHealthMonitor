"""
Django settings for SNMPHealthMonitor (Django version).
Config-driven layout: settings live in config/ not project_name/.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-change-me-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')


# Application definition
INSTALLED_APPS = [
    # Django Channels (must be before django apps for ASGI)
    'daphne',
    'channels',
    
    # Django built-ins
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Our apps
    'apps.core',
    'apps.devices',
    'apps.metrics',
    'apps.realtime',
    'apps.web',
    'apps.files',
    
    # Third party apps
    'django_extensions',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Enable WhiteNoise for static files
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
        'DIRS': [BASE_DIR / 'templates'],
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

# ASGI application (for Daphne + Channels)
ASGI_APPLICATION = 'config.asgi.application'

# WSGI application (fallback for traditional deployment)
WSGI_APPLICATION = 'config.wsgi.application'


# Database - MySQL via PyMySQL
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME', 'python_programming'),
        'USER': os.getenv('DB_USER', 'root'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
        },
    }
}


# Channel Layers - InMemory (No Redis required)
# WARNING: Only works for single-process deployments
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Ho_Chi_Minh'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'  # Required for WhiteNoise/collectstatic

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# =============================================================================
# SNMPHealthMonitor Specific Settings
# =============================================================================
# UDP Listener (for receiving metrics from rasberrypi collector)
UDP_LISTEN_HOST = os.getenv('UDP_LISTEN_HOST', '0.0.0.0')
UDP_LISTEN_PORT = int(os.getenv('UDP_LISTEN_PORT', '9999'))


# =============================================================================
# File Management Settings
# =============================================================================
HOME_DIRECTORY = os.path.abspath(os.path.expanduser(
    os.getenv('FILE_HOME_DIR', '~/managed_files')
))
TRASH_DIRECTORY = os.path.join(HOME_DIRECTORY, '.trash')
BACKUP_DIRECTORY = os.path.join(HOME_DIRECTORY, '.backups')
BACKUP_RETENTION = 10          # keep last N backups per file
MAX_EDIT_SIZE = 10 * 1024 * 1024  # 10 MB
ARCHIVE_EXTENSIONS = ('.zip', '.tar', '.tar.gz', '.tgz')
