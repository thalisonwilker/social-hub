"""Conexão de um perfil do Threads (OAuth → token curto → token longo → perfil → SocialAccount)."""
import logging
from datetime import timedelta

from django.utils import timezone

from apps.social.crypto import encrypt_token
from apps.social.models import SocialAccount

from .threads import ThreadsClient

logger = logging.getLogger("apps.social.meta")

STATE_KEY = "threads_oauth_state"


def connect_profile(user, code: str, client: ThreadsClient | None = None) -> SocialAccount:
    """Conclui o login: cria ou atualiza a conta (reconectar o mesmo perfil não duplica). O token curto não é guardado."""
    client = client or ThreadsClient.from_settings()
    short = client.exchange_code(code)
    long_lived = client.extend_token(short["access_token"])
    profile = client.get_profile(short["user_id"], long_lived["access_token"])

    now = timezone.now()
    account, _ = SocialAccount.objects.update_or_create(
        owner=user,
        platform=SocialAccount.Platform.THREADS,
        external_id=profile["id"] or short["user_id"],
        defaults={
            "name": profile["name"] or profile["username"],
            "username": profile["username"],
            "picture_url": profile["picture_url"],
            "category": "",
            "granted_tasks": [],
            "access_token_enc": encrypt_token(long_lived["access_token"]),
            "token_expires_at": now + timedelta(seconds=long_lived["expires_in"]),
            "token_refreshed_at": now,
            "status": SocialAccount.Status.ACTIVE,
            "last_error": "",
        },
    )
    logger.info("threads_connected account=%s", account.pk)
    return account
