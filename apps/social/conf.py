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


def _https_origin(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https" or not parsed.netloc:
        return ""
    return f"https://{parsed.netloc}"


def public_base_url() -> str:
    """Endereço público (origem HTTPS) pelo qual a Meta alcança o Hub. Nunca vem do cabeçalho Host.

    `PUBLIC_BASE_URL`; se vazio, a origem do `THREADS_REDIRECT_URI`. Vazio se nenhum for HTTPS.
    """
    return _https_origin(getattr(settings, "PUBLIC_BASE_URL", "")) or _https_origin(
        getattr(settings, "THREADS_REDIRECT_URI", "")
    )


def public_url_configured() -> bool:
    return bool(public_base_url())


def evolution_base_url() -> str:
    """Origem HTTPS da Evolution (spec 0006). Caminho, query e fragmento são descartados; vazio se inválida.

    Vem SEMPRE da configuração do servidor, nunca do usuário. URL com usuário/senha embutidos é recusada.
    """
    from urllib.parse import urlparse

    raw = (getattr(settings, "EVOLUTION_API_URL", "") or "").strip()
    parsed = urlparse(raw)
    if parsed.username or parsed.password or parsed.scheme != "https" or not parsed.hostname:
        return ""
    return _https_origin(raw)


def evolution_configured() -> bool:
    """True com URL HTTPS válida e chave de criptografia válida (para cifrar a chave da instância)."""
    return bool(evolution_base_url()) and _keys_are_valid()

