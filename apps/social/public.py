"""URL pública temporária e assinada da imagem de uma publicação (para a Meta baixar). Ver ADR-0008.

O token é assinado (HMAC com a SECRET_KEY) sobre o id da publicação e expira. Não há estado no banco.
A URL é sempre montada a partir do endereço público configurado, nunca do cabeçalho Host.
"""
from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

from .conf import public_base_url

SALT = "threads-public-image"
ROUTE = "/publico/imagem{ext}"


class PublicUrlNotConfigured(RuntimeError):
    pass


def _signer() -> TimestampSigner:
    return TimestampSigner(salt=SALT, sep=".")


def sign_image_token(publication_id: int) -> str:
    return _signer().sign(str(publication_id))


def read_image_token(token: str) -> tuple[int | None, str]:
    """Devolve (id da publicação, "") se o token vale; senão (None, "expired"|"invalid")."""
    if not token:
        return None, "invalid"
    try:
        value = _signer().unsign(token, max_age=settings.THREADS_IMAGE_URL_TTL_SECONDS)
        return int(value), ""
    except SignatureExpired:
        return None, "expired"
    except (BadSignature, ValueError):
        return None, "invalid"


def image_extension(content_type: str) -> str:
    return ".png" if content_type == "image/png" else ".jpg"


def build_public_image_url(publication) -> str:
    base = public_base_url()
    if not base:
        raise PublicUrlNotConfigured("Endereço público HTTPS não configurado.")
    ext = image_extension(publication.image_content_type)
    return f"{base}{ROUTE.format(ext=ext)}?t={sign_image_token(publication.pk)}"
