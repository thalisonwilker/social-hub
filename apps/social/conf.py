"""Leitura da configuração da integração com a Meta."""
from cryptography.fernet import Fernet
from django.conf import settings

REQUIRED_SETTINGS = (
    "META_APP_ID",
    "META_APP_SECRET",
    "META_LOGIN_CONFIG_ID",
    "META_REDIRECT_URI",
    "META_TOKEN_ENCRYPTION_KEY",
)


def encryption_keys() -> list[str]:
    raw = getattr(settings, "META_TOKEN_ENCRYPTION_KEY", "") or ""
    return [key.strip() for key in raw.split(",") if key.strip()]


def _keys_are_valid() -> bool:
    keys = encryption_keys()
    if not keys:
        return False
    try:
        for key in keys:
            Fernet(key.encode())
    except (ValueError, TypeError):
        return False
    return True


def meta_configured() -> bool:
    """True quando todas as variáveis META_* obrigatórias estão preenchidas e a chave é válida."""
    if not all(getattr(settings, name, "") for name in REQUIRED_SETTINGS):
        return False
    return _keys_are_valid()


THREADS_REQUIRED_SETTINGS = ("THREADS_APP_ID", "THREADS_APP_SECRET", "THREADS_REDIRECT_URI")


def threads_configured() -> bool:
    """True quando as variáveis THREADS_* estão preenchidas e há chave válida para cifrar os tokens."""
    if not all(getattr(settings, name, "") for name in THREADS_REQUIRED_SETTINGS):
        return False
    return _keys_are_valid()


def threads_redirect_host() -> str:
    """Host (com porta) do THREADS_REDIRECT_URI: a conexão deve ser iniciada por ele (cookie de sessão por host)."""
    from urllib.parse import urlparse

    return urlparse(getattr(settings, "THREADS_REDIRECT_URI", "") or "").netloc
