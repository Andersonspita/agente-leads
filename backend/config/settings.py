"""Configurações do Auditor de Sites.

Tudo que varia entre ambientes vem de variáveis de ambiente (ver `.env.example`).
Sem PostgreSQL/Redis configurados, o sistema roda em modo local: SQLite e jobs
em threads, o que basta para desenvolvimento e demonstração.
"""
import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in ("1", "true", "yes", "on")


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-troque-em-producao")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in os.getenv("CSRF_TRUSTED_ORIGINS", "http://localhost:5173").split(",") if o]
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
# Endereço onde ficam as prévias dos sites gerados (/s/<token>/). Use um host separado do painel:
# localmente 127.0.0.1 (o painel usa localhost); em produção, por exemplo, https://previa.seudominio.com.br.
SITES_BASE_URL = os.getenv("SITES_BASE_URL", "http://127.0.0.1:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "django_filters",
    "corsheaders",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "apps.accounts",
    "apps.core",
    "apps.geo",
    "apps.catalog",
    "apps.leads",
    "apps.audits",
    "apps.reports",
    "apps.sitebuilder",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",  # Django >= 4.2 mitiga BREACH com bytes aleatórios
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# Painel React compilado (frontend/dist): o Django serve o index.html em produção.
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates", FRONTEND_DIST],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=60
    )
}
IS_POSTGRES = DATABASES["default"]["ENGINE"].endswith("postgresql")
if DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    # SQLite de desenvolvimento: espera até 30 s por um lock em vez de falhar com "database is locked".
    DATABASES["default"].setdefault("OPTIONS", {}).update({
        "timeout": 30,
        # WAL: leituras não bloqueiam gravações; synchronous=NORMAL evita um fsync caro a cada commit.
        "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        "transaction_mode": "IMMEDIATE",
    })

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))

# Armazenamento de capturas/PDFs: S3 (ou MinIO) quando configurado, disco local caso contrário.
if os.getenv("AWS_STORAGE_BUCKET_NAME"):
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "sa-east-1")
    AWS_S3_ENDPOINT_URL = os.getenv("AWS_S3_ENDPOINT_URL") or None
    AWS_QUERYSTRING_AUTH = True
    AWS_DEFAULT_ACL = None

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sessões de 8 h (TRD 2.6)
SESSION_COOKIE_AGE = 8 * 60 * 60
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT = timedelta(minutes=15)
OTP_TOTP_ISSUER = "Auditor de Sites"
# Em desenvolvimento dá para desligar o 2FA; em produção ele é sempre exigido.
REQUIRE_2FA = env_bool("REQUIRE_2FA", not DEBUG)

CORS_ALLOWED_ORIGINS = [o for o in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o]
CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["apps.accounts.permissions.IsVerifiedUser"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

# Filas: Celery + Redis quando CELERY_BROKER_URL existe; senão, threads locais.
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL or None)
CELERY_TASK_ACKS_LATE = True  # jobs retomam após queda do worker
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ROUTES = {
    "apps.leads.tasks.*": {"queue": "discovery"},
    "apps.audits.tasks.run_audit": {"queue": "audit"},
    "apps.audits.tasks.ai_analysis": {"queue": "ai"},
    "apps.reports.tasks.render_report_pdf": {"queue": "reports"},
    "apps.core.tasks.*": {"queue": "maintenance"},
}
CELERY_BEAT_SCHEDULE = {
    "recheck-sites": {"task": "apps.leads.tasks.recheck_sites", "schedule": timedelta(days=30)},
    "expire-reports": {"task": "apps.reports.tasks.expire_reports", "schedule": timedelta(days=1)},
    "purge-old-artifacts": {"task": "apps.core.tasks.purge_old_artifacts", "schedule": timedelta(days=7)},
}

# Integrações externas (todas opcionais; sem chave, a etapa é marcada como "não medida").
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
# Fontes gratuitas: OpenStreetMap (Overpass) e descoberta do site pelo domínio do e-mail do CNPJ.
OSM_ENABLED = env_bool("OSM_ENABLED", True)
OVERPASS_URLS = [u for u in os.getenv(
    "OVERPASS_URLS",
    "https://overpass-api.de/api/interpreter,https://overpass.kumi.systems/api/interpreter",
).split(",") if u]
EMAIL_DOMAIN_DISCOVERY = env_bool("EMAIL_DOMAIN_DISCOVERY", True)
# IA da análise qualitativa. Provedores: "gemini" (plano gratuito do Google AI Studio), "anthropic"
# (Claude) ou "openai_compat" (Ollama local, OpenRouter, Groq…). Sem AI_PROVIDER, usa o primeiro com chave.
AI_PROVIDER = os.getenv("AI_PROVIDER", "").strip().lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")
AI_MODEL = os.getenv("AI_MODEL", "")  # ex.: gemini-2.5-flash, qwen3.5:4b (Ollama)
AI_BASE_URL = os.getenv("AI_BASE_URL", "")  # ex.: http://localhost:11434/v1 (Ollama)
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", "180"))
LIGHTHOUSE_CMD = os.getenv("LIGHTHOUSE_CMD", "")  # ex.: "npx lighthouse" ou "lighthouse"
LIGHTHOUSE_RUNS = int(os.getenv("LIGHTHOUSE_RUNS", "3"))  # mediana de 3 (plano 6.3)
MONTHLY_API_BUDGET_BRL = float(os.getenv("MONTHLY_API_BUDGET_BRL", "500"))

# Rastreamento responsável (PRD 1.6 / TRD 2.7)
CRAWLER_USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "AuditorDeSitesBot/1.0 (Horizon AJ Desenvolvimento; auditoria de sites publicos)",
)
CRAWLER_MAX_PAGES = int(os.getenv("CRAWLER_MAX_PAGES", "10"))
CRAWLER_PAGE_TIMEOUT = int(os.getenv("CRAWLER_PAGE_TIMEOUT", "60"))
CRAWLER_MIN_INTERVAL = float(os.getenv("CRAWLER_MIN_INTERVAL", "1.0"))
AUDIT_TIMEOUT = int(os.getenv("AUDIT_TIMEOUT", "300"))
AUDIT_PARALLELISM = int(os.getenv("AUDIT_PARALLELISM", "5"))

REPORT_DEFAULT_EXPIRY_DAYS = int(os.getenv("REPORT_DEFAULT_EXPIRY_DAYS", "60"))
ARTIFACT_RETENTION_DAYS = int(os.getenv("ARTIFACT_RETENTION_DAYS", "365"))
SEARCH_CACHE_DAYS = int(os.getenv("SEARCH_CACHE_DAYS", "30"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
}

if os.getenv("SENTRY_DSN"):
    import sentry_sdk

    sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), traces_sample_rate=0.1)
