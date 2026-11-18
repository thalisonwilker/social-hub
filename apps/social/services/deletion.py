"""Excluir publicações (spec 0010, ADR-0014): "Remover do Hub" (histórico + imagem) e "Apagar na plataforma" (Facebook e Threads).

- Duas ações separadas: apagar na plataforma NUNCA remove o registro; remover do Hub NUNCA chama a plataforma.
- Alvo apagado continua `published` com `deleted_at`. Resposta desconhecida nunca grava `deleted_at` (repetir é seguro).
- Instagram e WhatsApp não têm exclusão pelo Hub. Nada de token, id externo, texto ou corpo de resposta em log ou mensagem.
"""
import logging
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.social.conf import meta_configured, threads_configured
from apps.social.crypto import TokenCryptoError
from apps.social.models import Publication, PublicationTarget, SocialAccount

from . import threads_tokens
from .meta import MetaApiError
from .publishing import (
    BLOCKED_CODES,
    MSG_CREDENTIALS,
    MSG_NETWORK,
    MSG_RATE_LIMIT,
    MSG_REAUTH,
    MSG_THREADS_REAUTH,
    PERMISSION_CODES,
    RATE_LIMIT_CODES,
    TOKEN_CODES,
    ClientPool,
)

logger = logging.getLogger("apps.social.meta")

S = PublicationTarget.Status
P = SocialAccount.Platform
SUPPORTED = (P.FACEBOOK_PAGE, P.THREADS)
GONE_CODES = {(100, 33)}  # Graph: objeto inexistente (confirmar no UAT; Threads idem)

# Motivos de recusa (eligibility)
UNSUPPORTED, NOT_PUBLISHED, NO_POST_ID, ALREADY_DELETED, NO_ACCOUNT, NEEDS_REAUTH = (
    "unsupported", "not_published", "no_post_id", "already_deleted", "no_account", "needs_reauth",
)

MSG_REFUSED = {
    UNSUPPORTED: "O Hub não apaga posts desta plataforma. Apague pelo app.",
    NOT_PUBLISHED: "Só dá para apagar na plataforma um post que foi publicado.",
    NO_POST_ID: "O Hub não guardou o identificador deste post: apague pelo app.",
    ALREADY_DELETED: "Este post já foi apagado na plataforma.",
    NO_ACCOUNT: "A conta deste destino foi desconectada: apague pelo app.",
    NEEDS_REAUTH: "Reconecte a conta para apagar este post.",
}
MSG_DELETED = "Post apagado na plataforma."
MSG_ALREADY_GONE = "O post já não existia na plataforma: marcado como apagado."
MSG_DELETE_UNKNOWN = "Não foi possível confirmar a exclusão. Confira na plataforma e tente novamente."
MSG_DELETE_PERMISSION = "Sem permissão para apagar este post."
MSG_DELETE_THREADS_PERMISSION = "Sem permissão para apagar no Threads. Reconecte o Threads para conceder “apagar posts”."
MSG_NOT_CONFIGURED = "Integração não configurada."
MSG_DELETE_FAILED = "A plataforma recusou apagar este post."
MSG_REMOVE_SENDING = "Há envio em andamento: aguarde terminar para remover."


@dataclass(frozen=True)
class DeleteResult:
    outcome: str  # deleted | already_gone | refused | failed | unknown
    message: str

    @property
    def ok(self) -> bool:
        return self.outcome in ("deleted", "already_gone")


@dataclass
class BulkResult:
    deleted: int = 0
    failed: int = 0
    skipped: int = 0  # sem exclusão pelo Hub (plataforma sem suporte, conta ausente, já apagado…)
    results: list = field(default_factory=list)


def eligibility(target: PublicationTarget) -> str:
    """"" se o alvo é apagável na plataforma; senão o motivo (matriz da spec 0010)."""
    if target.platform not in SUPPORTED:
        return UNSUPPORTED
    if target.is_deleted:
        return ALREADY_DELETED
    if target.status != S.PUBLISHED:
        return NOT_PUBLISHED
    if not target.external_post_id:
        return NO_POST_ID
    if target.account_id is None:
        return NO_ACCOUNT
    if target.account.needs_reauth:
        return NEEDS_REAUTH
    return ""


def _mark_reauth(account: SocialAccount, code) -> None:
    SocialAccount.objects.filter(Q(pk=account.pk) | Q(parent_id=account.pk)).update(
        status=SocialAccount.Status.NEEDS_REAUTH, last_error=f"Meta erro {code}", last_checked_at=timezone.now()
    )


def _is_gone(exc: MetaApiError) -> bool:
    return exc.status == 404 or (exc.code, exc.subcode) in GONE_CODES


def _failure_message(exc: MetaApiError, platform: str) -> str:
    if exc.code in TOKEN_CODES or exc.status == 401:
        return MSG_THREADS_REAUTH if platform == P.THREADS else MSG_REAUTH
    if exc.code in PERMISSION_CODES or exc.code == "platform_not_supported":
        return MSG_DELETE_THREADS_PERMISSION if platform == P.THREADS else MSG_DELETE_PERMISSION
    if exc.code in RATE_LIMIT_CODES or exc.status == 429:
        return MSG_RATE_LIMIT
    if exc.code in BLOCKED_CODES:
        return MSG_DELETE_FAILED
    return MSG_DELETE_FAILED


def _mark_deleted(target: PublicationTarget) -> bool:
    updated = PublicationTarget.objects.filter(pk=target.pk, status=S.PUBLISHED, deleted_at__isnull=True).update(
        deleted_at=timezone.now()
    )
    return updated == 1


def delete_on_platform(target: PublicationTarget, pool: ClientPool | None = None) -> DeleteResult:
    """Apaga o post do alvo na plataforma. Nunca remove o registro; só grava `deleted_at` com confirmação (ou "já não existe")."""
    reason = eligibility(target)
    if reason:
        return DeleteResult("refused", MSG_REFUSED[reason])
    pool = pool or ClientPool()
    account, platform = target.account, target.platform
    try:
        if platform == P.THREADS:
            if not threads_configured():
                return DeleteResult("refused", MSG_NOT_CONFIGURED)
            client = pool.threads()
            if not threads_tokens.ensure_fresh(account, client=client):
                return DeleteResult("failed", MSG_THREADS_REAUTH)
            client.delete_media(target.external_post_id, account.get_token())
        else:
            if not meta_configured():
                return DeleteResult("refused", MSG_NOT_CONFIGURED)
            pool.graph().delete_post(target.external_post_id, account.get_token())
    except TokenCryptoError:
        return DeleteResult("failed", MSG_CREDENTIALS)
    except MetaApiError as exc:
        if exc.outcome_unknown:  # a exclusão pode ter acontecido: nada é gravado; repetir é seguro
            logger.warning("target_delete_unknown platform=%s code=%s", platform, exc.code)
            return DeleteResult("unknown", MSG_DELETE_UNKNOWN)
        if _is_gone(exc):
            _mark_deleted(target)
            logger.info("target_deleted platform=%s result=already_gone", platform)
            return DeleteResult("already_gone", MSG_ALREADY_GONE)
        if exc.is_token_error:
            _mark_reauth(account, exc.code or exc.status)
        logger.warning("target_delete_failed platform=%s code=%s", platform, exc.code or exc.status)
        return DeleteResult("failed", _failure_message(exc, platform))
    _mark_deleted(target)
    logger.info("target_deleted platform=%s result=ok", platform)
    return DeleteResult("deleted", MSG_DELETED)


def delete_publication_on_platform(publication: Publication, pool: ClientPool | None = None) -> BulkResult:
    """Tenta apagar cada alvo apagável; uma falha não impede os demais. Não remove nada do Hub."""
    pool = pool or ClientPool()
    bulk = BulkResult()
    for target in publication.targets.select_related("account").order_by("page_name", "id"):
        if eligibility(target):
            bulk.skipped += 1
            continue
        result = delete_on_platform(target, pool)
        bulk.results.append((target.pk, result))
        if result.ok:
            bulk.deleted += 1
        else:
            bulk.failed += 1
    return bulk


# --- Remover do Hub ------------------------------------------------------------------
def _delete_image_file(publication: Publication) -> None:
    name = publication.image.name
    if not name:
        return
    try:
        publication.image.storage.delete(name)
    except OSError:  # o banco é a fonte da verdade; arquivo órfão é só logado
        logger.warning("image_delete_failed")


def remove_publication(publication: Publication) -> bool:
    """Remove a publicação, seus alvos e a imagem. False (nada apagado) se há alvo `sending`."""
    with transaction.atomic():
        if publication.targets.filter(status=S.SENDING).exists():
            return False
        image_holder = Publication(image=publication.image.name)
        publication.delete()
    _delete_image_file(image_holder)
    logger.info("publication_removed")
    return True


def remove_target(target: PublicationTarget) -> str | None:
    """Remove um alvo; se era o último, remove a publicação. Devolve "target", "publication" ou None (alvo `sending`)."""
    publication = target.publication
    with transaction.atomic():
        if target.status == S.SENDING:
            return None
        others = publication.targets.exclude(pk=target.pk).exists()
        if others:
            target.delete()
            logger.info("target_removed")
            return "target"
    return "publication" if remove_publication(publication) else None
