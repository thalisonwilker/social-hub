"""Publicação de uma imagem com texto em várias Páginas (ADR-0004).

- Envio síncrono em lotes (`PUBLISH_BATCH_SIZE`); cada alvo é REIVINDICADO atomicamente antes da chamada.
- Alvo `published` nunca é reenviado; `sending` recente não é reenviado; `sending` antigo é recuperado.
- Erros viram mensagens amigáveis (nunca o texto cru da Meta). Nada de token ou texto da publicação em log.
"""
import logging
import os
import time
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.social.conf import public_url_configured, threads_configured
from apps.social.crypto import TokenCryptoError
from apps.social import public
from apps.social.images import SanitizedImage
from apps.social.models import Publication, PublicationTarget, SocialAccount

from . import threads_publish, threads_tokens
from .meta import GraphClient, MetaApiError
from .threads import ThreadsClient

logger = logging.getLogger("apps.social.meta")

STALE_SENDING = timedelta(minutes=5)
MIN_SECONDS_TO_START_TARGET = 40  # não inicia novo alvo com menos que isso no orçamento (ADR-0009)
WAIT_SAFETY_MARGIN = 25  # a espera do container sempre deixa esta folga para publicar e gravar
POST_URL = "https://www.facebook.com/{post_id}"

MSG_REAUTH = "Reconexão necessária para esta Página."
MSG_PERMISSION = "Sem permissão para publicar nesta Página."
MSG_RATE_LIMIT = "Limite de requisições da Meta. Tente mais tarde."
MSG_BLOCKED = "A Meta bloqueou esta publicação."
MSG_NETWORK = "Falha de comunicação com a Meta."
MSG_DISCONNECTED = "Conta desconectada."
MSG_CREDENTIALS = "Não foi possível ler as credenciais desta Página. Reconecte a conta."
MSG_IMAGE_MISSING = "A imagem da publicação não está disponível no servidor."
MSG_THREADS_REAUTH = "Reconexão necessária para este perfil do Threads."
MSG_THREADS_NOT_CONFIGURED = "Integração com o Threads não configurada."
MSG_THREADS_PENDING = "O Threads ainda está processando. Tente novamente."
MSG_THREADS_REJECTED = "O Threads recusou o conteúdo desta publicação."
MSG_THREADS_EXPIRED = "O envio ao Threads expirou. Tente novamente."
MSG_THREADS_IMAGE_REJECTED = "O Threads não conseguiu processar a imagem. Tente novamente."
MSG_THREADS_IMAGE_PENDING = "O Threads ainda está processando a imagem. Tente novamente."
MSG_THREADS_NO_PUBLIC_URL = "O endereço público do Hub não está configurado: não dá para enviar a imagem ao Threads."

TOKEN_CODES = {102, 190}
PERMISSION_CODES = {10, 200, 220}
RATE_LIMIT_CODES = {4, 17, 32, 613}
BLOCKED_CODES = {368}
NETWORK_CODES = {"network", "bad_response"}

S = PublicationTarget.Status


@dataclass(frozen=True)
class BatchResult:
    attempted: int  # alvos enviados à Meta nesta chamada
    published: int
    failed: int
    remaining: int  # alvos ainda pendentes (não couberam no lote)


# --- criação ------------------------------------------------------------------
def create_publication(owner, text: str, image: SanitizedImage | None, accounts) -> Publication:
    """Cria a publicação, grava a imagem (quando há) e um alvo `pending` por destino (uma transação).

    Publicações só do Threads não têm imagem (`image=None`).
    """
    publication = Publication(owner=owner, text=text, image_content_type=image.content_type if image else "")
    if image:
        publication.image.save(image.content.name, image.content, save=False)
    try:
        with transaction.atomic():
            publication.save()
            targets = PublicationTarget.objects.bulk_create(
                [
                    PublicationTarget(
                        publication=publication,
                        account=account,
                        page_external_id=account.external_id,
                        page_name=account.name,
                        platform=account.platform,
                    )
                    for account in accounts
                ]
            )
    except Exception:
        if image:
            publication.image.delete(save=False)  # não deixa arquivo órfão
        raise
    logger.info("publication_created targets=%d", len(targets))
    return publication


# --- reivindicação atômica ----------------------------------------------------
def claim_target(target_id: int) -> PublicationTarget | None:
    """Marca o alvo como `sending` só se ele puder ser enviado. Devolve None se outra requisição o tem."""
    now = timezone.now()
    was_sending = PublicationTarget.objects.filter(pk=target_id, status=S.SENDING).exists()
    claimable = Q(status__in=[S.PENDING, S.FAILED]) | Q(status=S.SENDING, last_attempt_at__lt=now - STALE_SENDING)
    updated = (
        PublicationTarget.objects.filter(claimable, pk=target_id, account__isnull=False)
        .update(status=S.SENDING, last_attempt_at=now, attempts=F("attempts") + 1)
    )
    if updated != 1:
        return None
    if was_sending:
        logger.warning("target_reclaimed target=%s", target_id)
    return PublicationTarget.objects.select_related("account", "publication").get(pk=target_id)


# --- envio --------------------------------------------------------------------
def send_pending(
    publication: Publication,
    *,
    client: GraphClient | None = None,
    threads_client: ThreadsClient | None = None,
    batch_size: int | None = None,
    clock=time.monotonic,
) -> BatchResult:
    """Envia até `batch_size` alvos pendentes/falhos de qualquer plataforma. Alvos `published` nunca são tocados.

    O lote é um TETO; o tempo manda (ADR-0009): com menos de 40 s restantes do orçamento
    (`PUBLISH_REQUEST_BUDGET_SECONDS`) nenhum novo alvo é iniciado e o resto fica `pending`.
    """
    limit = batch_size or settings.PUBLISH_BATCH_SIZE
    started_at = clock()
    budget = settings.PUBLISH_REQUEST_BUDGET_SECONDS
    candidates = list(
        publication.targets.filter(status__in=[S.PENDING, S.FAILED, S.SENDING]).select_related("account")
    )
    candidates.sort(key=lambda t: (t.status != S.PENDING, t.page_name, t.id))  # pendentes primeiro

    attempted = published = failed = 0
    for index, target in enumerate(candidates):
        if attempted >= limit:
            break
        if target.account_id is None:  # conta desconectada: falha sem chamar a Meta
            if not (target.status == S.FAILED and target.error_message == MSG_DISCONNECTED):
                _mark_failed(target, MSG_DISCONNECTED, "disconnected")
            continue
        remaining_time = budget - (clock() - started_at)
        if remaining_time < MIN_SECONDS_TO_START_TARGET:
            logger.warning("publish_budget_exhausted remaining=%d", len(candidates) - index)
            break
        claimed = claim_target(target.pk)
        if claimed is None:
            continue
        attempted += 1
        if claimed.platform == SocialAccount.Platform.THREADS:
            threads_client = threads_client or ThreadsClient.from_settings()
            ok = _publish_threads_target(claimed, threads_client, max_wait=remaining_time - WAIT_SAFETY_MARGIN)
        else:
            client = client or GraphClient.from_settings()
            ok = _publish_target(claimed, client)
        if ok:
            published += 1
        else:
            failed += 1

    remaining = publication.targets.filter(status=S.PENDING, account__isnull=False).count()
    logger.info("publish_batch size=%d ok=%d failed=%d", attempted, published, failed)
    return BatchResult(attempted=attempted, published=published, failed=failed, remaining=remaining)


def _publish_target(target: PublicationTarget, client: GraphClient) -> bool:
    account, publication = target.account, target.publication
    try:
        token = account.get_token()
        with publication.image.open("rb") as fh:
            result = client.publish_photo(
                account.external_id,
                token,
                image=fh,
                filename=os.path.basename(publication.image.name),
                content_type=publication.image_content_type,
                message=publication.text,
            )
    except TokenCryptoError:
        _mark_failed(target, MSG_CREDENTIALS, "crypto")
        return False
    except FileNotFoundError:
        _mark_failed(target, MSG_IMAGE_MISSING, "image_missing")
        return False
    except MetaApiError as exc:
        message = friendly_error(exc)
        if exc.is_token_error:
            SocialAccount.objects.filter(pk=account.pk).update(
                status=SocialAccount.Status.NEEDS_REAUTH,
                last_error=f"Meta erro {exc.code}",
                last_checked_at=timezone.now(),
            )
        _mark_failed(target, message, str(exc.code or "unknown"))
        return False

    post_id = result["post_id"]
    PublicationTarget.objects.filter(pk=target.pk).update(
        status=S.PUBLISHED,
        external_post_id=post_id,
        permalink=POST_URL.format(post_id=post_id),
        published_at=timezone.now(),
        error_message="",
        error_code="",
    )
    logger.info("publish_ok page=%s", target.page_external_id)
    return True


def _publish_threads_target(target: PublicationTarget, client: ThreadsClient, *, max_wait: float | None = None) -> bool:
    """Publica no Threads: imagem + texto se a publicação tem imagem, senão só texto. Resultado gravado no alvo.

    Se o container de imagem não fica pronto o alvo FALHA (reenviável); nunca vira só texto (spec 0005).
    """
    account, publication = target.account, target.publication
    if not threads_configured():
        _mark_failed(target, MSG_THREADS_NOT_CONFIGURED, "not_configured")
        return False
    try:
        if not threads_tokens.ensure_fresh(account, client=client):  # expirado/recusado: a conta já virou needs_reauth
            _mark_failed(target, MSG_THREADS_REAUTH, "reauth")
            return False
        token = account.get_token()
        if publication.has_image:
            if not target.external_container_id:
                if not public_url_configured():
                    _mark_failed(target, MSG_THREADS_NO_PUBLIC_URL, "no_public_url")
                    return False
                if not publication.image.storage.exists(publication.image.name):
                    _mark_failed(target, MSG_IMAGE_MISSING, "image_missing")
                    return False
            outcome = threads_publish.publish_image(
                target, client, token, publication.text, lambda: public.build_public_image_url(publication), max_wait=max_wait
            )
        else:
            outcome = threads_publish.publish_text(target, client, token, publication.text)
    except TokenCryptoError:
        _mark_failed(target, MSG_CREDENTIALS, "crypto")
        return False
    except threads_publish.ContainerNotReady:
        message = MSG_THREADS_IMAGE_PENDING if publication.has_image else MSG_THREADS_PENDING
        _mark_failed(target, message, "container_pending")  # mantém o container para retomar
        return False
    except threads_publish.ContainerFailed as exc:
        threads_publish.forget_container(target)  # próximo envio cria outro
        if publication.has_image:
            message = MSG_THREADS_IMAGE_REJECTED
        else:
            message = MSG_THREADS_EXPIRED if exc.status == threads_publish.EXPIRED else MSG_THREADS_REJECTED
        _mark_failed(target, message, exc.status.lower())
        return False
    except MetaApiError as exc:
        if exc.is_token_error:
            SocialAccount.objects.filter(pk=account.pk).update(
                status=SocialAccount.Status.NEEDS_REAUTH,
                last_error=f"Meta erro {exc.code or exc.status}",
                last_checked_at=timezone.now(),
            )
            _mark_failed(target, MSG_THREADS_REAUTH, str(exc.code or exc.status or "unknown"))
        else:
            _mark_failed(target, friendly_error(exc), str(exc.code or exc.status or "unknown"))
        return False

    PublicationTarget.objects.filter(pk=target.pk).update(
        status=S.PUBLISHED,
        external_post_id=outcome.post_id,
        permalink=outcome.permalink,
        published_at=timezone.now(),
        error_message="",
        error_code="",
    )
    logger.info("publish_ok page=%s platform=threads", target.page_external_id)
    return True


def _mark_failed(target: PublicationTarget, message: str, code: str) -> None:
    PublicationTarget.objects.filter(pk=target.pk).update(status=S.FAILED, error_message=message, error_code=code)
    logger.warning("publish_failed page=%s code=%s", target.page_external_id, code)


def friendly_error(exc: MetaApiError) -> str:
    code = exc.code
    if code in TOKEN_CODES:
        return MSG_REAUTH
    if code in PERMISSION_CODES:
        return MSG_PERMISSION
    if code in RATE_LIMIT_CODES or exc.status == 429:
        return MSG_RATE_LIMIT
    if code in BLOCKED_CODES:
        return MSG_BLOCKED
    if code in NETWORK_CODES:
        return MSG_NETWORK
    return f"A Meta recusou a publicação (código {code})." if code else "A Meta recusou a publicação."
