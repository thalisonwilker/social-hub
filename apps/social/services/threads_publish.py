"""Publicador do Threads: container (TEXT ou IMAGE) → espera o status → publica → permalink (ADR-0007, ADR-0008).

O id do container é GRAVADO no alvo antes de esperar/publicar, para retomar sem recriar (e sem duplicar).
Com imagem, a Meta baixa o arquivo de uma URL pública assinada do Hub; se o container não fica pronto o alvo
FALHA (nunca publica só o texto). Nada de token, URL assinada nem texto em log.
"""
import re
import logging
import time
from dataclasses import dataclass

from django.conf import settings

from apps.social.models import PublicationTarget

from .meta import MetaApiError
from .threads import ThreadsClient

logger = logging.getLogger("apps.social.meta")

POLL_INTERVAL = 2.0  # segundos entre consultas ao status do container de texto
IMAGE_POLL_INTERVAL = 3.0  # idem, container de imagem

FINISHED = "FINISHED"
PUBLISHED = "PUBLISHED"
IN_PROGRESS = "IN_PROGRESS"
ERROR = "ERROR"
EXPIRED = "EXPIRED"


class ContainerNotReady(Exception):
    """O container não ficou `FINISHED` dentro do tempo; o id é mantido para retomar."""


class ContainerFailed(Exception):
    """O container terminou em ERROR/EXPIRED; o id deve ser descartado (próximo envio cria outro)."""

    def __init__(self, status: str, error_message: str = ""):
        super().__init__(status)
        self.status = status
        self.error_message = error_message  # enum da Meta (já saneado); só vai ao log


@dataclass(frozen=True)
class PublishOutcome:
    post_id: str  # id da mídia publicada ("" se o container já constava como PUBLISHED)
    permalink: str  # "" se indisponível


def _remember_container(target: PublicationTarget, container_id: str) -> None:
    PublicationTarget.objects.filter(pk=target.pk).update(external_container_id=container_id)
    target.external_container_id = container_id


def forget_container(target: PublicationTarget) -> None:
    _remember_container(target, "")


def _safe_enum(value: str) -> str:
    """O `error_message` do container é um enum (ex.: FAILED_DOWNLOADING_VIDEO); só letras/dígitos/_ passam."""
    return re.sub(r"[^A-Za-z0-9_]", "", value or "")[:64]


def _wait_and_publish(target, client, token, container_id, *, limit, interval, sleep, clock) -> PublishOutcome:
    user_id = target.account.external_id
    started = clock()
    while True:
        info = client.container_status(container_id, token)
        status = info["status"]
        if status == FINISHED:
            break
        if status == PUBLISHED:  # já publicado numa tentativa anterior: não republica (evita post duplicado)
            logger.info("threads_container_already_published target=%s", target.pk)
            return PublishOutcome(post_id="", permalink="")
        if status in (ERROR, EXPIRED):
            code = _safe_enum(info.get("error_message", ""))
            logger.warning("threads_container_error target=%s status=%s code=%s", target.pk, status, code or "-")
            raise ContainerFailed(status, code)
        if clock() - started >= limit:
            raise ContainerNotReady()
        sleep(interval)
    logger.info("threads_container_ready target=%s wait_ms=%d", target.pk, int((clock() - started) * 1000))

    media_id = client.publish_container(user_id, token, container_id)
    try:
        permalink = client.get_permalink(media_id, token)
    except MetaApiError:
        permalink = ""  # melhor esforço: a publicação já aconteceu
    return PublishOutcome(post_id=media_id, permalink=permalink)


def publish_text(target: PublicationTarget, client: ThreadsClient, token: str, text: str, *, sleep=None, clock=None) -> PublishOutcome:
    """Publica `text` no perfil do alvo. Levanta ContainerNotReady/ContainerFailed/MetaApiError."""
    sleep, clock = sleep or time.sleep, clock or time.monotonic
    container_id = target.external_container_id
    if not container_id:
        container_id = client.create_text_container(target.account.external_id, token, text)
        _remember_container(target, container_id)  # antes de esperar: permite retomar se algo cair
        logger.info("threads_container_created target=%s", target.pk)
    return _wait_and_publish(
        target, client, token, container_id,
        limit=settings.THREADS_CONTAINER_WAIT_SECONDS, interval=POLL_INTERVAL, sleep=sleep, clock=clock,
    )


def publish_image(
    target: PublicationTarget,
    client: ThreadsClient,
    token: str,
    text: str,
    image_url_factory,
    *,
    max_wait: float | None = None,
    sleep=None,
    clock=None,
) -> PublishOutcome:
    """Publica imagem + `text`. `image_url_factory()` só é chamada ao CRIAR o container (retomada reutiliza o id).

    A espera é `min(THREADS_IMAGE_WAIT_SECONDS, max_wait)`; `max_wait` vem do orçamento da requisição.
    """
    sleep, clock = sleep or time.sleep, clock or time.monotonic
    container_id = target.external_container_id
    if not container_id:
        container_id = client.create_image_container(target.account.external_id, token, text, image_url_factory())
        _remember_container(target, container_id)
        logger.info("threads_image_container_created target=%s", target.pk)
    limit = settings.THREADS_IMAGE_WAIT_SECONDS
    if max_wait is not None:
        limit = min(limit, max(0.0, max_wait))
    return _wait_and_publish(
        target, client, token, container_id, limit=limit, interval=IMAGE_POLL_INTERVAL, sleep=sleep, clock=clock
    )
