"""Validação e sanitização das imagens de publicação. Ver ADR-0005.

Aceita apenas JPEG e PNG REAIS (pelo conteúdo, não pela extensão). A imagem é decodificada e
re-encodada: metadados (EXIF/GPS) e dados extras do arquivo original são descartados e o nome
original nunca é usado.
"""
import io
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG": ("image/jpeg", ".jpg"), "MPO": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png")}
JPEG_QUALITY = 92

MSG_TOO_BIG = "A imagem deve ter no máximo {mb} MB."
MSG_INVALID = "O arquivo enviado não é uma imagem válida."
MSG_FORMAT = "Use uma imagem JPEG ou PNG."
MSG_PIXELS = "A imagem é grande demais (dimensões acima do limite permitido)."


class ImageValidationError(ValueError):
    """Erro de validação com mensagem amigável, própria para exibir ao usuário."""


@dataclass(frozen=True)
class SanitizedImage:
    content: ContentFile  # nome aleatório já definido
    content_type: str
    extension: str
    width: int = 0
    height: int = 0

    def aspect_ratio_within(self, limit: float) -> bool:
        """True se max(l,a)/min(l,a) <= limit (nos dois sentidos)."""
        return aspect_ratio_within(self.width, self.height, limit)


def aspect_ratio_within(width: int, height: int, limit: float) -> bool:
    if width <= 0 or height <= 0:
        return False
    return max(width, height) <= limit * min(width, height)


def sanitize_image(upload) -> SanitizedImage:
    max_bytes = settings.PUBLICATION_MAX_IMAGE_BYTES
    max_pixels = settings.PUBLICATION_MAX_IMAGE_PIXELS

    if upload is None or not getattr(upload, "size", 0):
        raise ImageValidationError(MSG_INVALID)
    if upload.size > max_bytes:
        raise ImageValidationError(MSG_TOO_BIG.format(mb=max_bytes // (1024 * 1024)))

    try:
        upload.seek(0)
        image = Image.open(upload)  # leitura preguiçosa: só o cabeçalho
        fmt = image.format
        width, height = image.size
        if fmt not in ALLOWED_FORMATS:
            raise ImageValidationError(MSG_FORMAT)
        if width * height > max_pixels:
            raise ImageValidationError(MSG_PIXELS)
        image.load()  # decodifica de verdade: arquivo corrompido/falso falha aqui
    except ImageValidationError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageValidationError(MSG_INVALID) from None

    content_type, extension = ALLOWED_FORMATS[fmt]
    image = ImageOps.exif_transpose(image)  # aplica a orientação ANTES de descartar o EXIF
    width, height = image.size  # após a orientação (a proporção vale para a imagem final)
    out = io.BytesIO()
    if content_type == "image/jpeg":
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)  # sem exif=, sem icc_profile=
    else:
        image.save(out, format="PNG", optimize=True)  # sem pnginfo: chunks de texto/EXIF descartados
    name = f"{uuid.uuid4().hex}{extension}"
    return SanitizedImage(content=ContentFile(out.getvalue(), name=name), content_type=content_type, extension=extension, width=width, height=height)


def to_jpeg_bytes(handle) -> bytes:
    """Converte uma imagem JÁ sanitizada (JPEG ou PNG) em JPEG para o Instagram (spec 0009).

    Transparência é achatada sobre fundo branco; só a entrega muda, a imagem armazenada não.
    """
    image = Image.open(handle)
    image.load()
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()
