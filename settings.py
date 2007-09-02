# Django settings for menclave project.

#================================= DEBUGGING =================================#

# Debug mode.  When enabled, makes pretty error pages and other useful things.
DEBUG = True
TEMPLATE_DEBUG = DEBUG

# If DEBUG is False, then any errors will be emailed to the ADMINS.
ADMINS = (('Nice-Write', 'nice-write@mit.edu'),)

# Information about broken links gets emailed to the MANAGERS.
SEND_BROKEN_LINK_EMAILS = True
MANAGERS = ADMINS

# Subject prefix for emails sent out to ADMINS or MANAGERS.
EMAIL_SUBJECT_PREFIX = '[NR3] '

HOST_NAME = "reverend.mit.edu:8000"

#================================= SESSIONS ==================================#

SESSION_COOKIE_AGE = 60 * 60 * 24 * 3  # three days (in seconds)
SESSION_COOKIE_SECURE = False  # TODO change to True for deployment
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # Don't leave cookies lying around.

#================================= DATABASE ==================================#

DATABASE_ENGINE = 'sqlite3'  # 'postgresql', 'mysql', 'sqlite3' or 'ado_mssql'.
DATABASE_NAME = '/var/media-enclave/database'
  # Or path to database file if using sqlite3.
DATABASE_USER = ''      # Not used with sqlite3.
DATABASE_PASSWORD = ''  # Not used with sqlite3.
DATABASE_HOST = ''  # Set to empty string for localhost. Not used with sqlite3.
DATABASE_PORT = ''  # Set to empty string for default. Not used with sqlite3.

#=================================== MISC ====================================#

# Local time zone for this installation. All choices can be found here:
# http://www.postgresql.org/docs/8.1/static/datetime-keywords.html#DATETIME-TIMEZONE-SET-TABLE
TIME_ZONE = 'America/New_York'

# Language code for this installation. All choices can be found here:
# http://www.w3.org/TR/REC-html40/struct/dirlang.html#langcodes
# http://blogs.law.harvard.edu/tech/stories/storyReader$15
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = False

# Absolute path to the directory that holds media.
# Example: "/home/media/media.lawrence.com/"
MEDIA_ROOT = '/var/media-enclave/media/'

# URL that handles the media served from MEDIA_ROOT.
# Example: "http://media.lawrence.com"
MEDIA_URL = '/media/'

# URL prefix for admin media -- CSS, JavaScript and images. Make sure to use a
# trailing slash.
# Examples: "http://foo.com/media/", "/media/".
ADMIN_MEDIA_PREFIX = '/admin-media/'

# Make this unique, and don't share it with anybody.
SECRET_KEY = '!am-u*02x(#hfrti+jcqj^pph5$@_5!)^^gz=kq3f73u7h*j%e'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.load_template_source',
    'django.template.loaders.app_directories.load_template_source',
#   'django.template.loaders.eggs.load_template_source',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.middleware.doc.XViewMiddleware',
)

ROOT_URLCONF = 'menclave.urls'

TEMPLATE_DIRS = (
    # Put strings here, like "/home/html/django_templates" or "C:/www/django/templates".
    # Always use forward slashes, even on Windows.
    # Don't forget to use absolute paths, not relative paths.
)

INSTALLED_APPS = (
    'django.contrib.admin',  # gives us an admin site
    'django.contrib.auth',  # gives us users and groups
    'django.contrib.contenttypes',  # here by default; don't know what it's for
    'django.contrib.humanize',  # lets us use a few extra template filters
    'django.contrib.sessions',  # handles user logins
    'menclave.aenclave',  # Audio Enclave
    'menclave.genclave',  # Gaming Enclave
    #'menclave.penclave',  # Pyrotechnics Enclave
    'menclave.venclave',  # Video Enclave
)

#=========================== DATE/TIME FORMATTING ============================#

# See all available format strings here:
# http://www.djangoproject.com/documentation/templates/#now

DATE_FORMAT = 'j M Y'             # 3 Dec 2006
DATETIME_FORMAT = 'j M Y H:i:s'   # 3 Dec 2006 15:34:12
TIME_FORMAT = 'H:i:s'             # 15:34:12
YEAR_MONTH_FORMAT = 'F Y'         # December 2006
MONTH_DAY_FORMAT = 'j F'          # 3 December

#=============================================================================#
