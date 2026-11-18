"""Rotas públicas da imagem de uma publicação, para a Meta baixar (Threads e Instagram). Ver ADR-0008 e ADR-0013.

É a ÚNICA rota anônima de mídia. Escopo mínimo: só serve com token assinado e válido, publicação com imagem
e ao menos um alvo DA PLATAFORMA da rota em andamento (Threads ou Instagram). Toda recusa é um 404 idêntico (não revela o motivo); o motivo
vai só ao log, sem token nem URL.
"""
import logging

from django.contrib.auth.decorators import login_not_required
from django.http import FileResponse, HttpResponse, HttpResponseNotFound
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .models import Publication, PublicationTarget
from .images import to_jpeg_bytes
from .public import image_extension, read_image_token

logger = logging.getLogger("apps.social.meta")

IN_FLIGHT = (
    PublicationTarget.Status.PENDING,
    PublicationTarget.Status.SENDING,
    PublicationTarget.Status.FAILED,
)


def _harden(response):
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["X-Robots-Tag"] = "noindex"
    return response


def _not_found(reason: str):
    logger.info("public_image_rejected reason=%s", reason)
    return _harden(HttpResponseNotFound(b"", content_type="text/plain"))


@method_decorator(csrf_exempt, name="dispatch")  # POST etc. devem chegar ao view e receber 405
@method_decorator(login_not_required, name="dispatch")
class PublicImageView(View):
    http_method_names = ["get", "head"]

    platform = "threads"

    def _resolve(self, request, ext):
        publication_id, reason = read_image_token(request.GET.get("t", ""))
        if publication_id is None:
            return None, _not_found(reason)
        publication = Publication.objects.filter(pk=publication_id).first()
        if publication is None or not publication.has_image:
            return None, _not_found("no_image")
        if ext is not None and image_extension(publication.image_content_type) != f".{ext}":
            return None, _not_found("invalid")
        in_flight = publication.targets.filter(platform=self.platform, status__in=IN_FLIGHT).exists()
        if not in_flight:
            return None, _not_found("not_in_flight")
        return publication, None

    def get(self, request, ext):
        publication, refusal = self._resolve(request, ext)
        if refusal:
            return refusal
        try:
            handle = publication.image.open("rb")
        except FileNotFoundError:
            return _not_found("no_image")
        logger.info("public_image_served")
        return _harden(FileResponse(handle, content_type=publication.image_content_type))

    def head(self, request, ext):
        publication, refusal = self._resolve(request, ext)
        if refusal:
            return refusal
        response = HttpResponse(b"", content_type=publication.image_content_type)
        try:
            response["Content-Length"] = str(publication.image.size)
        except (FileNotFoundError, OSError):
            return _not_found("no_image")
        logger.info("public_image_served")
        return _harden(response)


class PublicInstagramImageView(PublicImageView):
    """`/publico/instagram.jpg`: sempre JPEG (PNG é convertido só na entrega); só com alvo Instagram em andamento."""

    platform = "instagram"

    def _jpeg(self, publication):
        try:
            with publication.image.open("rb") as handle:
                if publication.image_content_type == "image/jpeg":
                    return handle.read()
                return to_jpeg_bytes(handle)
        except (FileNotFoundError, OSError, ValueError):
            return None

    def get(self, request, ext=None):
        publication, refusal = self._resolve(request, None)
        if refusal:
            return refusal
        body = self._jpeg(publication)
        if body is None:
            return _not_found("no_image")
        logger.info("public_image_served")
        return _harden(HttpResponse(body, content_type="image/jpeg"))

    def head(self, request, ext=None):
        publication, refusal = self._resolve(request, None)
        if refusal:
            return refusal
        body = self._jpeg(publication)
        if body is None:
            return _not_found("no_image")
        response = HttpResponse(b"", content_type="image/jpeg")
        response["Content-Length"] = str(len(body))
        logger.info("public_image_served")
        return _harden(response)
