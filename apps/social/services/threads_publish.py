"""Publicador de texto do Threads: container → espera o status → publica → permalink (ADR-0007).

O id do container é GRAVADO no alvo antes de esperar/publicar, para retomar sem recriar (e sem duplicar).
Nenhuma imagem é enviada ao Threads nesta etapa. Nada de token nem texto em log.
"""
import logging
import time
from dataclasses import dataclass

from django.conf import settings

from apps.social.models import PublicationTarget

from .meta import MetaApiError
from .threads import ThreadsClient

logger = logging.getLogger("apps.social.meta")

POLL_INTERVAL = 2.0  # segundos entre consultas ao status do container

FINISHED = "FINISHED"
PUBLISHED = "PUBLISHED"
IN_PROGRESS = "IN_PROGRESS"
ERROR = "ERROR"
EXPIRED = "EXPIRED"


class ContainerNotReady(Exception):
    """O container não ficou `FINISHED` dentro do tempo; o id é mantido para retomar."""


class ContainerFailed(Exception):
    """O container terminou em ERROR/EXPIRED; o id deve ser descartado (próximo envio cria outro)."""

    def __init__(self, status: str):
        super().__init__(status)
        self.status = status


@dataclass(frozen=True)
class PublishOutcome:
    post_id: str  # id da mídia publicada ("" se o container já constava como PUBLISHED)
    permalink: str  # "" se indisponível


def _remember_container(target: PublicationTarget, container_id: str) -> None:
    PublicationTarget.objects.filter(pk=target.pk).update(external_container_id=container_id)
    target.external_container_id = container_id


def forget_container(target: PublicationTarget) -> None:
    _remember_container(target, "")


def publish_text(target: PublicationTarget, client: ThreadsClient, token: str, text: str, *, sleep=time.sleep, clock=time.monotonic) -> PublishOutcome:
    """Publica `text` no perfil do alvo. Levanta ContainerNotReady/ContainerFailed/MetaApiError."""
    user_id = target.account.external_id
    container_id = target.external_container_id
    if not container_id:
        container_id = client.create_text_container(user_id, token, text)
        _remember_container(target, container_id)  # antes de esperar: permite retomar se algo cair
        logger.info("threads_container_created target=%s", target.pk)

    started = clock()
    limit = settings.THREADS_CONTAINER_WAIT_SECONDS
    while True:
        status = client.container_status(container_id, token)["status"]
        if status == FINISHED:
            break
        if status == PUBLISHED:  # já publicado numa tentativa anterior: não republica (evita post duplicado)
            logger.info("threads_container_already_published target=%s", target.pk)
            return PublishOutcome(post_id="", permalink="")
        if status in (ERROR, EXPIRED):
            raise ContainerFailed(status)
        if clock() - started >= limit:
            raise ContainerNotReady()
        sleep(POLL_INTERVAL)
    logger.info("threads_container_ready target=%s wait_ms=%d", target.pk, int((clock() - started) * 1000))

    media_id = client.publish_container(user_id, token, container_id)
    try:
        permalink = client.get_permalink(media_id, token)
    except MetaApiError:
        permalink = ""  # melhor esforço: a publicação já aconteceu
    return PublishOutcome(post_id=media_id, permalink=permalink)
