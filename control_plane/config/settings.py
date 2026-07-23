from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv
from corsheaders.defaults import default_headers

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent
load_dotenv(REPO_ROOT / ".env")


def repo_path(name: str, default: Path) -> Path:
    value = Path(os.getenv(name, str(default)))
    return value if value.is_absolute() else (REPO_ROOT / value).resolve()


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "development-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = (
    ["*"]
    if DEBUG
    else [item.strip() for item in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost").split(",") if item.strip()]
)

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "api",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "api.middleware.AuditMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'kubeops.sqlite3'}",
        conn_max_age=60,
    )
}

AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOWED_ORIGINS = [
    item.strip()
    for item in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if item.strip()
]
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOW_HEADERS = [
    *default_headers,
    "x-kubeops-organization",
    "x-kubeops-workspace",
    "x-request-id",
]

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["api.permissions.KubeOpsRolePermission"],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("KUBEOPS_ANON_RATE", "120/hour"),
        "user": os.getenv("KUBEOPS_USER_RATE", "1200/hour"),
    },
}

KUBEOPS_SCENARIO_DIR = repo_path("KUBEOPS_SCENARIO_DIR", REPO_ROOT / "scenarios")
KUBEOPS_ARTIFACT_DIR = repo_path("KUBEOPS_ARTIFACT_DIR", REPO_ROOT / "artifacts")
KUBEOPS_ARTIFACT_BACKEND = os.getenv("KUBEOPS_ARTIFACT_BACKEND", "file").lower()
KUBEOPS_ARTIFACT_S3_BUCKET = os.getenv("KUBEOPS_ARTIFACT_S3_BUCKET", "")
KUBEOPS_ARTIFACT_S3_PREFIX = os.getenv("KUBEOPS_ARTIFACT_S3_PREFIX", "kubeops")
KUBEOPS_ARTIFACT_S3_ENDPOINT = os.getenv("KUBEOPS_ARTIFACT_S3_ENDPOINT")
KUBEOPS_ARTIFACT_S3_REGION = os.getenv("KUBEOPS_ARTIFACT_S3_REGION")
KUBEOPS_PROFILE_DIR = repo_path("KUBEOPS_PROFILE_DIR", REPO_ROOT / "profiles")
KUBEOPS_LIFECYCLE_DIR = repo_path("KUBEOPS_LIFECYCLE_DIR", REPO_ROOT / "lifecycle")
KUBEOPS_POLICY_DIR = repo_path("KUBEOPS_POLICY_DIR", REPO_ROOT / "policies")
KUBEOPS_OPERATION_DIR = repo_path("KUBEOPS_OPERATION_DIR", REPO_ROOT / "operations")
KUBEOPS_PACK_DIR = repo_path("KUBEOPS_PACK_DIR", REPO_ROOT / "packs")
KUBEOPS_ENABLED_PACKS = [item.strip() for item in os.getenv("KUBEOPS_ENABLED_PACKS", "").split(",") if item.strip()]
KUBEOPS_LIVE_EXECUTION_ENABLED = os.getenv("KUBEOPS_LIVE_EXECUTION_ENABLED", "0") == "1"

KUBEOPS_ALLOW_ANONYMOUS_READ = os.getenv("KUBEOPS_ALLOW_ANONYMOUS_READ", "1" if DEBUG else "0") == "1"
KUBEOPS_DEFAULT_ORGANIZATION_ID = os.getenv("KUBEOPS_DEFAULT_ORGANIZATION_ID", "default")
KUBEOPS_DEFAULT_WORKSPACE_ID = os.getenv("KUBEOPS_DEFAULT_WORKSPACE_ID", "default")
KUBEOPS_BACKUP_DIR = repo_path("KUBEOPS_BACKUP_DIR", REPO_ROOT / "backups")
KUBEOPS_RETENTION_APPLY_ENABLED = os.getenv("KUBEOPS_RETENTION_APPLY_ENABLED", "0") == "1"
KUBEOPS_AUDIT_REQUIRED = os.getenv("KUBEOPS_AUDIT_REQUIRED", "0" if DEBUG else "1") == "1"
KUBEOPS_PACK_TRUST_KEY_ID = os.getenv("KUBEOPS_PACK_TRUST_KEY_ID", "release-key")
KUBEOPS_PACK_TRUST_SECRET_ENV = os.getenv("KUBEOPS_PACK_TRUST_SECRET_ENV", "KUBEOPS_PACK_TRUST_SECRET")
KUBEOPS_PACK_TRUST_PUBLIC_KEY_ENV = os.getenv("KUBEOPS_PACK_TRUST_PUBLIC_KEY_ENV", "KUBEOPS_PACK_TRUST_PUBLIC_KEY")
KUBEOPS_EXECUTOR_OFFLINE_SECONDS = int(os.getenv("KUBEOPS_EXECUTOR_OFFLINE_SECONDS", "120"))

if not DEBUG:
    if SECRET_KEY == "development-only-change-me" or len(SECRET_KEY) < 32:
        raise RuntimeError("DJANGO_SECRET_KEY must be a non-default value of at least 32 characters")
    if not ALLOWED_HOSTS or ALLOWED_HOSTS == [""]:
        raise RuntimeError("DJANGO_ALLOWED_HOSTS must be configured in production")
    if KUBEOPS_ARTIFACT_BACKEND == "s3" and not KUBEOPS_ARTIFACT_S3_BUCKET:
        raise RuntimeError("KUBEOPS_ARTIFACT_S3_BUCKET is required for the S3 artifact backend")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "0") == "1"
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "0") == "1"
    SECURE_HSTS_PRELOAD = os.getenv("DJANGO_SECURE_HSTS_PRELOAD", "0") == "1"
