"""Publicação de uma imagem com texto em várias Páginas (ADR-0004).

- Cada alvo é REIVINDICADO atomicamente (`pending → sending`) antes da chamada; só `pending` é reivindicado (spec 0007).
- Alvo `published` nunca é reenviado; `sending` NÃO volta sozinho para a fila: se o resultado é desconhecido
  (chamada com efeito sem resposta, worker reiniciado, `sending` vencido) o alvo vira `uncertain` e só o usuário resolve.
- `send_pending` é o envio na requisição (modo `inline`, lote + orçamento); o worker usa `process_target` sem orçamento.
- Erros viram mensagens amigáveis (nunca o texto cru da Meta). Nada de token ou texto da publicação em log.
"""
import logging
import os
import time
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import OperationalError, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.social.conf import evolution_configured, meta_configured, public_url_configured, threads_configured
from apps.social.crypto import TokenCryptoError
from apps.social import public
from apps.social.images import SanitizedImage
from apps.social.models import Publication, PublicationTarget, SocialAccount

from . import evolution_connect, instagram_publish, threads_publish, threads_tokens
from .evolution import EvolutionApiError, EvolutionClient
from .meta import GraphClient, MetaApiError
from .threads import ThreadsClient

logger = logging.getLogger("apps.social.meta")

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
MSG_UNCERTAIN = "Não foi possível confirmar se foi publicado. Confira na plataforma e escolha “Já foi publicado” ou “Reenviar”."
MSG_IMAGE_MISSING = "A imagem da publicação não está disponível no servidor."
MSG_THREADS_REAUTH = "Reconexão necessária para este perfil do Threads."
MSG_THREADS_NOT_CONFIGURED = "Integração com o Threads não configurada."
MSG_THREADS_PENDING = "O Threads ainda está processando. Tente novamente."
MSG_THREADS_REJECTED = "O Threads recusou o conteúdo desta publicação."
MSG_THREADS_EXPIRED = "O envio ao Threads expirou. Tente novamente."
MSG_THREADS_IMAGE_REJECTED = "O Threads não conseguiu processar a imagem. Tente novamente."
MSG_THREADS_IMAGE_PENDING = "O Threads ainda está processando a imagem. Tente novamente."
MSG_THREADS_NO_PUBLIC_URL = "O endereço público do Hub não está configurado: não dá para enviar a imagem ao Threads."

MSG_IG_REAUTH = "Reconexão necessária para esta conta do Instagram."
MSG_IG_PENDING = "O Instagram ainda está processando a imagem. Tente novamente."
MSG_IG_IMAGE_REJECTED = "O Instagram não conseguiu processar a imagem. Tente novamente."
MSG_IG_NO_PUBLIC_URL = "O endereço público do Hub não está configurado: não dá para enviar a imagem ao Instagram."
MSG_IG_NO_IMAGE = "O Instagram só publica com imagem, e esta publicação não tem imagem."
MSG_META_NOT_CONFIGURED = "Integração com a Meta não configurada."

MSG_WHATSAPP_NOT_CONFIGURED = "Integração com o WhatsApp não configurada."
MSG_WHATSAPP_REAUTH = "Reconecte o número na Evolution."
MSG_WHATSAPP_NETWORK = "Falha de comunicação com a Evolution."
MSG_WHATSAPP_RATE_LIMIT = "Limite de requisições. Tente mais tarde."
MSG_WHATSAPP_REJECTED = "A Evolution recusou este conteúdo."
MSG_CREDENTIALS_WHATSAPP = "Não foi possível ler a chave desta instância. Atualize a conta."

TOKEN_CODES = {102, 190}
PERMISSION_CODES = {10, 200, 220}
RATE_LIMIT_CODES = {4, 9, 17, 32, 613}
BLOCKED_CODES = {368}
NETWORK_CODES = {"network", "bad_response", "timeout", "interrupted"}

S = PublicationTarget.Status


@dataclass(frozen=True)
class BatchResult:
    attempted: int  # alvos enviados à Meta nesta chamada
    published: int
    failed: int
    remaining: int  # alvos ainda pendentes (não couberam no lote)
    uncertain: int = 0  # alvos que ficaram Incertos (resultado desconhecido; o usuário resolve)


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


# --- reivindicação atômica e transições ----------------------------------------
def claim_target(target_id: int) -> PublicationTarget | None:
    """`pending → sending`, atômico. Só `pending` com conta é reivindicado; devolve None se outro processo o tem.

    Nunca reivindica `sending`/`failed`/`uncertain`/`published` (spec 0007: sem recuperação automática).
    """
    try:
        updated = (
            PublicationTarget.objects.filter(pk=target_id, status=S.PENDING, account__isnull=False)
            .update(status=S.SENDING, last_attempt_at=timezone.now(), attempts=F("attempts") + 1)
        )
    except OperationalError:  # `database is locked`: o worker repete no ciclo seguinte; nenhuma transição se perde
        logger.warning("claim_locked target=%s", target_id)
        return None
    if updated != 1:
        return None
    return PublicationTarget.objects.select_related("account", "publication").get(pk=target_id)


def requeue_target(target_id: int) -> bool:
    """"Tentar novamente": `failed → pending`, atômico, só com a conta conectada. Nunca toca `published`/`uncertain`."""
    updated = PublicationTarget.objects.filter(pk=target_id, status=S.FAILED, account__isnull=False).update(
        status=S.PENDING, error_message="", error_code=""
    )
    return updated == 1


def requeue_failed(publication: Publication) -> int:
    """Reenfileira os alvos `failed` (com conta) da publicação. Devolve quantos voltaram a `pending`."""
    ids = list(publication.targets.filter(status=S.FAILED, account__isnull=False).values_list("pk", flat=True))
    return sum(1 for pk in ids if requeue_target(pk))


def resolve_as_published(target_id: int) -> bool:
    """"Já foi publicado": `uncertain → published` (atômico), sem link nem id externo. Funciona sem conta. Só vale para `uncertain`."""
    updated = PublicationTarget.objects.filter(pk=target_id, status=S.UNCERTAIN).update(
        status=S.PUBLISHED, published_at=timezone.now(), error_message="", error_code="", permalink="", external_post_id=""
    )
    if updated:
        logger.info("target_resolved action=published")
    return updated == 1


def resolve_resend(target_id: int) -> bool:
    """"Reenviar": `uncertain → pending` (atômico), só com conta. O usuário assume o risco de duplicar o post."""
    updated = PublicationTarget.objects.filter(pk=target_id, status=S.UNCERTAIN, account__isnull=False).update(
        status=S.PENDING, error_message="", error_code=""
    )
    if updated:
        logger.info("target_resolved action=resend")
    return updated == 1


def recover_sending(*, reason: str, older_than: timedelta | None = None) -> int:
    """`sending → uncertain` (NUNCA para `pending`): o dono do alvo morreu ou passou do prazo e o resultado é desconhecido."""
    queryset = PublicationTarget.objects.filter(status=S.SENDING)
    if older_than is not None:
        queryset = queryset.filter(last_attempt_at__lt=timezone.now() - older_than)
    count = queryset.update(status=S.UNCERTAIN, error_message=MSG_UNCERTAIN, error_code=reason)
    if count:
        logger.warning("target_uncertain reason=%s n=%d", reason, count)
    return count


def recover_stale_sending() -> int:
    """Alvos `sending` além de `PUBLISH_SENDING_STALE_SECONDS` viram Incertos (`stale`)."""
    return recover_sending(reason="stale", older_than=timedelta(seconds=settings.PUBLISH_SENDING_STALE_SECONDS))


class ClientPool:
    """Clientes das plataformas, criados só quando usados (e injetáveis nos testes)."""

    def __init__(self, graph: GraphClient | None = None, threads: ThreadsClient | None = None, evolution: EvolutionClient | None = None):
        self._graph, self._threads, self._evolution = graph, threads, evolution

    def graph(self) -> GraphClient:
        self._graph = self._graph or GraphClient.from_settings()
        return self._graph

    def threads(self) -> ThreadsClient:
        self._threads = self._threads or ThreadsClient.from_settings()
        return self._threads

    def evolution(self) -> EvolutionClient | None:
        if self._evolution is None and evolution_configured():
            self._evolution = EvolutionClient.from_settings()
        return self._evolution


def process_target(
    target_id: int, pool: ClientPool, *, threads_max_wait: float | None = None, evolution_timeout: float | None = None
) -> str | None:
    """Reivindica e envia UM alvo pela sua plataforma. Devolve o estado final (`published`/`failed`/`uncertain`) ou None se não o reivindicou.

    Usado pelo envio na requisição (com orçamento: `threads_max_wait`/`evolution_timeout` limitados) e pelo worker (sem orçamento).
    """
    claimed = claim_target(target_id)
    if claimed is None:
        return None
    return dispatch_claimed(claimed, pool, threads_max_wait=threads_max_wait, evolution_timeout=evolution_timeout)


def dispatch_claimed(
    claimed: PublicationTarget, pool: ClientPool, *, threads_max_wait: float | None = None, evolution_timeout: float | None = None
) -> str:
    """Envia um alvo JÁ reivindicado (`sending`) pela sua plataforma e devolve o estado final gravado."""
    if claimed.platform == SocialAccount.Platform.THREADS:
        _publish_threads_target(claimed, pool.threads(), max_wait=threads_max_wait)
    elif claimed.platform == SocialAccount.Platform.INSTAGRAM:
        _publish_instagram_target(claimed, pool.graph(), max_wait=threads_max_wait)
    elif claimed.platform == SocialAccount.Platform.WHATSAPP_STATUS:
        _publish_whatsapp_target(claimed, pool.evolution(), timeout=evolution_timeout)
    else:
        _publish_target(claimed, pool.graph())
    return PublicationTarget.objects.filter(pk=claimed.pk).values_list("status", flat=True).first()


def mark_disconnected(target: PublicationTarget) -> None:
    """Alvo sem conta (desconectada): `failed` sem chamar a plataforma (não reenviável)."""
    if not (target.status == S.FAILED and target.error_message == MSG_DISCONNECTED):
        _mark_failed(target, MSG_DISCONNECTED, "disconnected")


def mark_unexpected_error(target_id: int) -> None:
    """Exceção inesperada depois da reivindicação: não se sabe se a plataforma chegou a publicar → Incerto (`worker_error`)."""
    PublicationTarget.objects.filter(pk=target_id, status=S.SENDING).update(
        status=S.UNCERTAIN, error_message=MSG_UNCERTAIN, error_code="worker_error"
    )
    logger.warning("target_uncertain reason=worker_error n=1")


# --- envio na requisição (modo inline) ------------------------------------------
def send_pending(
    publication: Publication,
    *,
    client: GraphClient | None = None,
    threads_client: ThreadsClient | None = None,
    evolution_client: EvolutionClient | None = None,
    batch_size: int | None = None,
    clock=time.monotonic,
) -> BatchResult:
    """Envia na requisição até `batch_size` alvos pendentes/falhos de qualquer plataforma (modo `inline`).

    O lote é um TETO; o tempo manda (ADR-0009): com menos de 40 s restantes do orçamento
    (`PUBLISH_REQUEST_BUDGET_SECONDS`) nenhum novo alvo é iniciado e o resto fica `pending`.
    Alvo `failed` volta a `pending` (atômico) antes de ser reivindicado; `uncertain` nunca é reenviado aqui.
    """
    recover_stale_sending()
    pool = ClientPool(client, threads_client, evolution_client)
    limit = batch_size or settings.PUBLISH_BATCH_SIZE
    started_at = clock()
    budget = settings.PUBLISH_REQUEST_BUDGET_SECONDS
    candidates = list(publication.targets.filter(status__in=[S.PENDING, S.FAILED]).select_related("account"))
    candidates.sort(key=lambda t: (t.status != S.PENDING, t.page_name, t.id))  # pendentes primeiro

    attempted = published = failed = uncertain = 0
    for index, target in enumerate(candidates):
        if attempted >= limit:
            break
        if target.account_id is None:  # conta desconectada: falha sem chamar a plataforma
            mark_disconnected(target)
            continue
        remaining_time = budget - (clock() - started_at)
        if remaining_time < MIN_SECONDS_TO_START_TARGET:
            logger.warning("publish_budget_exhausted remaining=%d", len(candidates) - index)
            break
        if target.status == S.FAILED and not requeue_target(target.pk):
            continue
        # A chamada nunca passa do orçamento: min(config, restante − folga). A sondagem de estado (≤ 10 s) cabe na folga.
        outcome = process_target(
            target.pk,
            pool,
            threads_max_wait=remaining_time - WAIT_SAFETY_MARGIN,
            evolution_timeout=min(settings.EVOLUTION_TIMEOUT_SECONDS, remaining_time - WAIT_SAFETY_MARGIN),
        )
        if outcome is None:
            continue
        attempted += 1
        if outcome == S.PUBLISHED:
            published += 1
        elif outcome == S.UNCERTAIN:
            uncertain += 1
        else:
            failed += 1

    remaining = publication.targets.filter(status=S.PENDING, account__isnull=False).count()
    logger.info("publish_batch size=%d ok=%d failed=%d uncertain=%d", attempted, published, failed, uncertain)
    return BatchResult(attempted=attempted, published=published, failed=failed, remaining=remaining, uncertain=uncertain)


def _uncertain_code(exc) -> str:
    return exc.code if exc.code in ("timeout", "interrupted") else "interrupted"


def _mark_uncertain(target: PublicationTarget, code: str) -> None:
    """Resultado desconhecido: o alvo vira `uncertain` (nunca é reenviado sozinho). Log só com o motivo."""
    PublicationTarget.objects.filter(pk=target.pk).update(status=S.UNCERTAIN, error_message=MSG_UNCERTAIN, error_code=code)
    logger.warning("target_uncertain reason=%s n=1", code)


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
        if exc.outcome_unknown:  # o upload foi enviado e a resposta não veio: a Meta pode ter publicado
            _mark_uncertain(target, _uncertain_code(exc))
            return False
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
        if exc.outcome_unknown:  # `threads_publish` enviado sem resposta: o Threads pode ter publicado
            _mark_uncertain(target, _uncertain_code(exc))
            return False
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


def _mark_instagram_reauth(account: SocialAccount, code) -> None:
    """Token recusado: o Instagram usa o token da Página, então AMBAS as contas pedem reconexão."""
    ids = [account.pk] + ([account.parent_id] if account.parent_id else [])
    SocialAccount.objects.filter(pk__in=ids).update(
        status=SocialAccount.Status.NEEDS_REAUTH, last_error=f"Meta erro {code}", last_checked_at=timezone.now()
    )


def _publish_instagram_target(target: PublicationTarget, client: GraphClient, *, max_wait: float | None = None) -> bool:
    """Publica no Instagram: imagem + legenda (spec 0009). Resultado gravado no alvo.

    Container que não fica pronto → FALHA reenviável; `media_publish` sem resposta → INCERTO (nunca reenvia sozinho).
    """
    account, publication = target.account, target.publication
    if not meta_configured():
        _mark_failed(target, MSG_META_NOT_CONFIGURED, "not_configured")
        return False
    if account.needs_reauth:  # não chama a Meta até a conta voltar a ficar ativa
        _mark_failed(target, MSG_IG_REAUTH, "reauth")
        return False
    if not publication.has_image:
        _mark_failed(target, MSG_IG_NO_IMAGE, "no_image")
        return False
    try:
        token = account.get_token()
        if not target.external_container_id:
            if not public_url_configured():
                _mark_failed(target, MSG_IG_NO_PUBLIC_URL, "no_public_url")
                return False
            if not publication.image.storage.exists(publication.image.name):
                _mark_failed(target, MSG_IMAGE_MISSING, "image_missing")
                return False
        outcome = instagram_publish.publish_image(
            target, client, token, publication.text, lambda: public.build_instagram_image_url(publication), max_wait=max_wait
        )
    except TokenCryptoError:
        _mark_failed(target, MSG_CREDENTIALS, "crypto")
        return False
    except instagram_publish.ContainerNotReady:
        _mark_failed(target, MSG_IG_PENDING, "container_pending")  # mantém o container para retomar
        return False
    except instagram_publish.ContainerFailed as exc:
        instagram_publish.forget_container(target)  # próximo envio cria outro, com nova URL
        _mark_failed(target, MSG_IG_IMAGE_REJECTED, exc.status.lower())
        return False
    except MetaApiError as exc:
        if exc.outcome_unknown:  # `media_publish` enviado sem resposta: o Instagram pode ter publicado
            _mark_uncertain(target, _uncertain_code(exc))
            return False
        if exc.is_token_error:
            _mark_instagram_reauth(account, exc.code or exc.status)
            _mark_failed(target, MSG_IG_REAUTH, str(exc.code or exc.status or "unknown"))
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
    logger.info("publish_ok page=%s platform=instagram", target.page_external_id)
    return True


STATE_PROBE_CODES = {"rejected", "server", "bad_response"}  # falhas que podem ser "instância fora de `open`"
STATE_PROBE_TIMEOUT = 10  # a sondagem é curta: não pode comer o orçamento da requisição


def _publish_whatsapp_target(target: PublicationTarget, client: EvolutionClient | None, *, timeout: float | None = None) -> bool:
    """Publica o Status no WhatsApp via Evolution: texto, ou imagem (base64) com o texto como legenda. Uma chamada, sem espera.

    Chave inválida/instância inexistente/desconectada → conta em Reconexão necessária (spec 0006, AC-11).
    Nada de chave, base64 ou texto em log ou mensagem.
    """
    account, publication = target.account, target.publication
    if client is None:
        _mark_failed(target, MSG_WHATSAPP_NOT_CONFIGURED, "not_configured")
        return False
    if account.needs_reauth:  # não chama a Evolution até a conta voltar a ficar ativa
        _mark_failed(target, MSG_WHATSAPP_REAUTH, "reauth")
        return False
    try:
        key = account.get_token()
        if publication.has_image:
            with publication.image.open("rb") as fh:
                image = fh.read()
            message_id = client.send_status_image(
                account.external_id, key, image, publication.text,
                content_type=publication.image_content_type, timeout=timeout,
            )
        else:
            message_id = client.send_status_text(account.external_id, key, publication.text, timeout=timeout)
    except TokenCryptoError:
        _mark_failed(target, MSG_CREDENTIALS_WHATSAPP, "crypto")
        return False
    except FileNotFoundError:
        _mark_failed(target, MSG_IMAGE_MISSING, "image_missing")
        return False
    except EvolutionApiError as exc:
        if exc.outcome_unknown:  # `sendStatus` enviado sem resposta: a Evolution pode ter publicado (UAT: duplicou)
            _mark_uncertain(target, _uncertain_code(exc))
            return False
        _mark_failed(target, _whatsapp_failure_message(exc, account, key, client), exc.code)
        return False

    PublicationTarget.objects.filter(pk=target.pk).update(
        status=S.PUBLISHED,
        external_post_id=message_id,
        permalink="",
        published_at=timezone.now(),
        error_message="",
        error_code="",
    )
    logger.info("evolution_status_sent kind=%s", "image" if publication.has_image else "text")
    return True


def _whatsapp_failure_message(exc: EvolutionApiError, account: SocialAccount, key: str, client: EvolutionClient) -> str:
    """Mensagem amigável da falha; marca a conta para reconexão quando a causa é a instância/chave."""
    code = exc.code
    if code in evolution_connect.REAUTH_CODES:
        evolution_connect.needs_reauth(account)
        return MSG_WHATSAPP_REAUTH
    if code in STATE_PROBE_CODES and _instance_not_open(client, account, key):
        evolution_connect.needs_reauth(account)
        return MSG_WHATSAPP_REAUTH
    if code == "rate_limit":
        return MSG_WHATSAPP_RATE_LIMIT
    if code == "rejected":
        return MSG_WHATSAPP_REJECTED
    if code == "not_configured":
        return MSG_WHATSAPP_NOT_CONFIGURED
    return MSG_WHATSAPP_NETWORK


def _instance_not_open(client: EvolutionClient, account: SocialAccount, key: str) -> bool:
    """Sonda o estado da conexão depois de uma falha ambígua. Se a sondagem falha, não conclui nada (False)."""
    try:
        return client.connection_state(account.external_id, key, timeout=STATE_PROBE_TIMEOUT) != evolution_connect.OPEN
    except EvolutionApiError:
        return False


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
