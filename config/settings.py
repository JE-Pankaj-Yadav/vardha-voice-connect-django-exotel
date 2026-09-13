from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() == "true"

# Render provides the public hostname automatically. Local development keeps
# the familiar localhost/127.0.0.1 defaults.
render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
configured_hosts = [x.strip() for x in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if x.strip()]
ALLOWED_HOSTS = list(dict.fromkeys(configured_hosts + ([render_hostname] if render_hostname else [])))

configured_csrf = [x.strip() for x in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]
if render_hostname:
    configured_csrf.append(f"https://{render_hostname}")
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(configured_csrf))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "voice_agent",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "voice_agent" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ]},
    }
]

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "data" / "db.sqlite3",
        }
    }

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("DEFAULT_TIMEZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ASGI_THREADS = 4
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

APP_NAME = os.getenv("APP_NAME", "Vardha Voice Connect — AI Voice Calling Agent")
APP_VERSION = os.getenv("APP_VERSION", "1.2.1")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().strip('"').strip("'").rstrip("/")
# On Render, use the hostname assigned to the web service unless a custom
# PUBLIC_BASE_URL is explicitly supplied. This removes the localhost/WSS
# configuration mistake that previously blocked calls after deployment.
if not PUBLIC_BASE_URL and render_hostname:
    PUBLIC_BASE_URL = f"https://{render_hostname}"
PUBLIC_BASE_URL_PLACEHOLDERS = (
    "your-public-domain.example.com",
    "example.com",
    "your-domain.com",
    "yourdomain.com",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
)
PUBLIC_BASE_URL_IS_PLACEHOLDER = (
    not PUBLIC_BASE_URL
    or not PUBLIC_BASE_URL.startswith("https://")
    or any(token in PUBLIC_BASE_URL.lower() for token in PUBLIC_BASE_URL_PLACEHOLDERS)
)

# Render terminates TLS before forwarding traffic to Daphne. These settings
# let Django correctly understand the original HTTPS request.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

def env_first(*names, default=""):
    """Return the first non-empty environment value, with whitespace/quotes normalized."""
    for name in names:
        value = os.getenv(name, "")
        if value is not None:
            value = str(value).strip().strip('"').strip("'").strip()
            if value:
                return value
    return default

# Accept both the current names and the common names used by older Vardha builds.
EXOTEL_ACCOUNT_SID = env_first("EXOTEL_ACCOUNT_SID", "EXOTEL_SID")
EXOTEL_API_KEY = env_first("EXOTEL_API_KEY", "EXOTEL_APIKEY")
EXOTEL_API_TOKEN = env_first("EXOTEL_API_TOKEN", "EXOTEL_TOKEN")
EXOTEL_CALLER_ID = env_first("EXOTEL_CALLER_ID", "EXOTEL_CALLERID", "EXOTEL_EXOPHONE")
# Exotel API domain is derived from the Account SID.
# A SID ending in "m" uses the Mumbai/India API domain; other SIDs use
# the global/Singapore API domain.  We intentionally do NOT trust a stale
# EXOTEL_API_BASE value from an older .env because a wrong region causes
# Exotel HTTP 401 / Code 34010.
EXOTEL_EXPECTED_API_BASE = (
    "https://api.in.exotel.com"
    if EXOTEL_ACCOUNT_SID.lower().endswith("m")
    else "https://api.exotel.com"
)
_configured_exotel_base = os.getenv("EXOTEL_API_BASE", "").strip().strip('"').strip("'").rstrip("/")
EXOTEL_API_BASE = EXOTEL_EXPECTED_API_BASE
EXOTEL_API_BASE_WAS_OVERRIDDEN = bool(_configured_exotel_base and _configured_exotel_base != EXOTEL_EXPECTED_API_BASE)

EXOTEL_STREAM_AUDIO_CONTENT_TYPE = os.getenv("EXOTEL_STREAM_AUDIO_CONTENT_TYPE", "audio/x-l16;rate=8000")
EXOTEL_STREAMTYPE = os.getenv("EXOTEL_STREAMTYPE", "bidirectional")
try:
    EXOTEL_STREAM_SAMPLE_RATE = int(os.getenv("EXOTEL_STREAM_SAMPLE_RATE", "8000"))
except ValueError:
    EXOTEL_STREAM_SAMPLE_RATE = 8000
if EXOTEL_STREAM_SAMPLE_RATE not in {8000, 16000, 24000}:
    EXOTEL_STREAM_SAMPLE_RATE = 8000
EXOTEL_RECORD = os.getenv("EXOTEL_RECORD", "true").lower() == "true"
EXOTEL_TIME_LIMIT = int(os.getenv("EXOTEL_TIME_LIMIT", "1800"))
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower() or "gemini"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_LIVE_MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview").strip()
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-3.1-flash-lite").strip()
GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Kore").strip()

# Optional legacy OpenAI settings. They remain available for future provider fallback.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
OPENAI_TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.6-luna")
OPENAI_VOICE = os.getenv("OPENAI_VOICE", "alloy")
OPENAI_REALTIME_INPUT_FORMAT = os.getenv("OPENAI_REALTIME_INPUT_FORMAT", "audio/pcm")
OPENAI_REALTIME_OUTPUT_FORMAT = os.getenv("OPENAI_REALTIME_OUTPUT_FORMAT", "audio/pcm")
