"""Renovação sob demanda do token do Threads (ADR-0006).

Não há worker: a renovação acontece quando o usuário usa o sistema (publicar / Verificar).
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.social.models import SocialAccount

from .meta import MetaApiError
from .threads import ThreadsClient

logger = logging.getLogger("apps.social.meta")

MIN_TOKEN_AGE = timedelta(hours=24)  # a Meta só renova tokens com pelo menos 24 h de vida


def _mark_needs_reauth(account: SocialAccount, reason: str, now) -> None:
    account.status = SocialAccount.Status.NEEDS_REAUTH
    account.last_error = reason
    account.last_checked_at = now
    account.save(update_fields=["status", "last_error", "last_checked_at", "updated_at"])


def ensure_fresh(account: SocialAccount, *, client: ThreadsClient | None = None, now=None) -> bool:
    """Garante que o token do Threads é utilizável. Devolve False se a conta virou `needs_reauth`.

    - já expirou → `needs_reauth`, sem chamada à rede;
    - faltam menos que `THREADS_REFRESH_WINDOW_DAYS` e o token tem ≥ 24 h → renova;
    - erro de token na renovação → `needs_reauth`; outro erro → mantém o token atual e segue.
    Tokens sem validade (Páginas do Facebook) são ignorados.
    """
    now = now or timezone.now()
    if account.token_expires_at is None:
        return True

    if account.token_expired(now):
        _mark_needs_reauth(account, "Token do Threads expirado", now)
        logger.warning("threads_token_expired account=%s", account.pk)
        return False

    window = timedelta(days=settings.THREADS_REFRESH_WINDOW_DAYS)
    old_enough = account.token_refreshed_at is None or now - account.token_refreshed_at >= MIN_TOKEN_AGE
    if account.token_expires_at - now >= window or not old_enough:
        return True

    client = client or ThreadsClient.from_settings()
    try:
        data = client.refresh_token(account.get_token())
    except MetaApiError as exc:
        if exc.is_token_error:
            _mark_needs_reauth(account, f"Meta erro {exc.code}", now)
            return False
        return True  # falha passageira: segue com o token atual, ainda válido

    account.set_token(data["access_token"])
    account.token_expires_at = now + timedelta(seconds=data["expires_in"])
    account.token_refreshed_at = now
    account.last_error = ""
    account.save(update_fields=["access_token_enc", "token_expires_at", "token_refreshed_at", "last_error", "updated_at"])
    logger.info("threads_token_refreshed account=%s", account.pk)
    return True
