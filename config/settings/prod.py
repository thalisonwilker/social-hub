"""Produção: DEBUG desligado, SECRET_KEY obrigatória e cabeçalhos de segurança."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env_bool, env_list

DEBUG = False

if len(SECRET_KEY) < 32 or SECRET_KEY.startswith("dev-only"):
    raise ImproperlyConfigured(
        "Defina DJANGO_SECRET_KEY (mín. 32 caracteres) no arquivo .env. "
        "Gere uma com: python -c \"import secrets; print(secrets.token_urlsafe(50))\""
    )

# 'localhost' e '127.0.0.1' são sempre aceitos para o healthcheck do container.
ALLOWED_HOSTS = list(
    dict.fromkeys(env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1") + ["localhost", "127.0.0.1"])
)
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# HTTPS: ative com DJANGO_SECURE_SSL=true quando houver TLS (ex.: proxy reverso).
# Mantido desligado por padrão para o sistema funcionar em http://localhost.
SECURE_SSL = env_bool("DJANGO_SECURE_SSL", False)
SESSION_COOKIE_SECURE = SECURE_SSL
CSRF_COOKIE_SECURE = SECURE_SSL
SECURE_SSL_REDIRECT = SECURE_SSL
SECURE_HSTS_SECONDS = 31536000 if SECURE_SSL else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_SSL
if env_bool("DJANGO_BEHIND_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]  # healthcheck do Docker usa HTTP puro
