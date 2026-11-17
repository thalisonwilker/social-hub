"""Configurações comuns a todos os ambientes.

Valores sensíveis ou específicos do ambiente vêm de variáveis de ambiente
(ou do arquivo `.env`, carregado automaticamente se existir).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Variáveis já definidas no ambiente (ex.: Docker) têm precedência sobre o .env.
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps do projeto
    "apps.core",
    "apps.accounts",
    "apps.dashboard",
    "apps.social",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Exige login em todas as views, exceto as marcadas com @login_not_required.
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# SQLite em modo WAL: melhor concorrência de leitura/escrita para um app pequeno.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DATABASE_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Publicações: imagens enviadas ficam em MEDIA_ROOT (volume persistente) e NÃO têm URL pública
# (MEDIA_URL não é definido); são entregues por view autenticada. Ver ADR-0005.
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", str(BASE_DIR / "media")))
PUBLISH_BATCH_SIZE = int(os.environ.get("PUBLISH_BATCH_SIZE", "5"))
PUBLICATION_MAX_IMAGE_BYTES = 8 * 1024 * 1024
PUBLICATION_MAX_IMAGE_PIXELS = 40_000_000
PUBLICATION_MAX_TEXT_LENGTH = 5000

# Integração com a Meta (Facebook). Se faltar algo, a feature fica desabilitada (apps.social.conf).
META_APP_ID = os.environ.get("META_APP_ID", "")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
META_LOGIN_CONFIG_ID = os.environ.get("META_LOGIN_CONFIG_ID", "")
META_REDIRECT_URI = os.environ.get("META_REDIRECT_URI", "")
META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v27.0")
# Uma ou mais chaves Fernet separadas por vírgula (a primeira criptografa; todas descriptografam).
META_TOKEN_ENCRYPTION_KEY = os.environ.get("META_TOKEN_ENCRYPTION_KEY", "")
META_HTTP_TIMEOUT = 10  # segundos, por chamada à Graph API
META_UPLOAD_TIMEOUT = 30  # segundos, por upload de imagem (lote de 5 => 150 s < Gunicorn --timeout 180)

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:index"
LOGOUT_REDIRECT_URL = "accounts:login"

LANGUAGE_CODE = "pt-br"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "America/Sao_Paulo")
USE_I18N = True
USE_TZ = True

# Arquivos estáticos: os assets compilados (Tailwind etc.) ficam em static/dist.
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
    # urllib3 em DEBUG registra URLs completas; mantém em WARNING para não vazar nada.
    "loggers": {"urllib3": {"level": "WARNING"}},
}
