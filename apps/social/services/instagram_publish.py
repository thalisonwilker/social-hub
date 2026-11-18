"""Publicador do Instagram: container (imagem + legenda) → espera o status → publica → permalink (spec 0009, ADR-0013).

O id do container é GRAVADO no alvo antes de esperar/publicar, para retomar sem recriar (e sem duplicar).
O Instagram baixa a imagem de uma URL pública JPEG assinada do Hub; se o container não fica pronto o alvo FALHA
(nunca publica sem a imagem). `media_publish` é a chamada com efeito: sem resposta, o resultado é desconhecido
(a quem chama: Incerto). Nada de token, URL assinada nem legenda em log.
"""
import logging
import time
from dataclasses import dataclass

from django.conf import settings

from apps.social.models import PublicationTarget

from .meta import GraphClient, MetaApiError

logger = logging.getLogger("apps.social.meta")

POLL_INTERVAL = 3.0  # segundos entre consultas ao status do container

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


def publish_image(
    target: PublicationTarget,
    client: GraphClient,
    token: str,
    caption: str,
    image_url_factory,
    *,
    max_wait: float | None = None,
    sleep=None,
    clock=None,
) -> PublishOutcome:
    """Publica imagem + `caption`. `image_url_factory()` só é chamada ao CRIAR o container (a retomada reutiliza o id).

    A espera é `min(INSTAGRAM_CONTAINER_WAIT_SECONDS, max_wait)`; `max_wait` vem do orçamento da requisição (modo inline).
    Levanta ContainerNotReady / ContainerFailed / MetaApiError (com `outcome_unknown` só em `media_publish`).
    """
    sleep, clock = sleep or time.sleep, clock or time.monotonic
    ig_id = target.account.external_id
    container_id = target.external_container_id
    if not container_id:
        container_id = client.create_instagram_container(ig_id, token, image_url_factory(), caption)
        _remember_container(target, container_id)  # antes de esperar: permite retomar se algo cair
        logger.info("instagram_container_created target=%s", target.pk)

    limit = settings.INSTAGRAM_CONTAINER_WAIT_SECONDS
    if max_wait is not None:
        limit = min(limit, max(0.0, max_wait))
    started = clock()
    while True:
        status = client.instagram_container_status(container_id, token)["status"]
        if status == FINISHED:
            break
        if status == PUBLISHED:  # já publicado numa tentativa anterior: não republica (evita post duplicado)
            logger.info("instagram_container_already_published target=%s", target.pk)
            return PublishOutcome(post_id="", permalink="")
        if status in (ERROR, EXPIRED):
            logger.warning("instagram_container_error target=%s code=%s", target.pk, status)
            raise ContainerFailed(status)
        if clock() - started >= limit:
            raise ContainerNotReady()
        sleep(POLL_INTERVAL)
    logger.info("instagram_container_ready target=%s wait_ms=%d", target.pk, int((clock() - started) * 1000))

    media_id = client.publish_instagram_container(ig_id, token, container_id)
    try:
        permalink = client.get_instagram_permalink(media_id, token)
    except MetaApiError:
        permalink = ""  # melhor esforço: a publicação já aconteceu
    return PublishOutcome(post_id=media_id, permalink=permalink)
