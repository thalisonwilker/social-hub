"""Orquestra a conexão de Páginas do Facebook (OAuth → seleção → SocialAccount).

Estado temporário na sessão do Django:
- `fb_oauth_state`: state de uso único (TTL 10 min).
- `fb_pending`: Páginas aguardando seleção, com o token de cada uma JÁ criptografado (TTL 10 min).
O token de usuário nunca é guardado.
"""
import logging
import secrets
import time
from dataclasses import dataclass

from django.db import transaction

from apps.social.crypto import encrypt_token
from apps.social.models import SocialAccount

from .meta import GraphClient

logger = logging.getLogger("apps.social.meta")

STATE_KEY = "fb_oauth_state"
PENDING_KEY = "fb_pending"
TTL_SECONDS = 600


class SelectionError(Exception):
    """Seleção inválida. `reason`: expired | empty | unknown."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class FetchResult:
    usable: int  # Páginas disponíveis para seleção
    skipped: int  # Páginas sem token (sem papel suficiente)


# --- state (anti-CSRF) --------------------------------------------------------
def new_state(session, key: str = STATE_KEY) -> str:
    state = secrets.token_urlsafe(32)
    session[key] = {"value": state, "exp": time.time() + TTL_SECONDS}
    return state


def consume_state(session, received: str, key: str = STATE_KEY) -> bool:
    """Valida e consome o state (uso único). `key` permite reutilizar a regra em outras plataformas."""
    stored = session.pop(key, None)
    if not stored or not received:
        return False
    if time.time() > stored.get("exp", 0):
        return False
    return secrets.compare_digest(str(stored.get("value", "")), received)


# --- descoberta de Páginas ----------------------------------------------------
def fetch_pages(session, code: str, client: GraphClient | None = None) -> FetchResult:
    """Troca o code por tokens e guarda as Páginas (cifradas) na sessão para seleção."""
    client = client or GraphClient.from_settings()
    user_token = client.extend_token(client.exchange_code(code))
    pages = client.list_pages(user_token)

    usable = [p for p in pages if p["access_token"]]
    skipped = len(pages) - len(usable)

    session.pop(PENDING_KEY, None)
    if usable:
        session[PENDING_KEY] = {
            "exp": time.time() + TTL_SECONDS,
            "pages": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "category": p["category"],
                    "picture_url": p["picture_url"],
                    "tasks": p["tasks"],
                    "instagram": p.get("instagram"),  # resumo sem token (spec 0009)
                    "token_enc": encrypt_token(p["access_token"]),
                }
                for p in usable
            ],
        }
    logger.info("oauth_completed pages=%d skipped=%d", len(usable), skipped)
    return FetchResult(usable=len(usable), skipped=skipped)


def pending_pages(session) -> list[dict] | None:
    """Páginas pendentes de seleção, ou None se não houver/expirou."""
    pending = session.get(PENDING_KEY)
    if not pending:
        return None
    if time.time() > pending.get("exp", 0):
        session.pop(PENDING_KEY, None)
        return None
    return pending["pages"]


# --- confirmação da seleção ---------------------------------------------------
def save_selected(user, session, selected_ids) -> list[SocialAccount]:
    """Cria/atualiza uma SocialAccount para cada Página marcada; limpa a sessão."""
    pages = pending_pages(session)
    if pages is None:
        raise SelectionError("expired")

    selected = list(dict.fromkeys(str(i) for i in selected_ids))  # sem duplicatas, ordem estável
    if not selected:
        raise SelectionError("empty")
    by_id = {p["id"]: p for p in pages}
    if any(i not in by_id for i in selected):
        raise SelectionError("unknown")

    accounts = []
    with transaction.atomic():
        for page_id in selected:
            page = by_id[page_id]
            account, _ = SocialAccount.objects.update_or_create(
                owner=user,
                platform=SocialAccount.Platform.FACEBOOK_PAGE,
                external_id=page_id,
                defaults={
                    "name": page["name"],
                    "category": page["category"],
                    "picture_url": page["picture_url"],
                    "granted_tasks": page["tasks"],
                    "access_token_enc": page["token_enc"],  # já criptografado
                    "status": SocialAccount.Status.ACTIVE,
                    "last_error": "",
                },
            )
            accounts.append(account)
            if "instagram" in page:  # sessões sem o campo (anteriores à 0009) não mexem nas contas Instagram
                _sync_instagram(user, account, page)
    session.pop(PENDING_KEY, None)
    logger.info("account_connected count=%d", len(accounts))
    return accounts


def _sync_instagram(user, page_account: SocialAccount, page: dict) -> None:
    """Cria/atualiza a Conta Instagram da Página (mesmo token cifrado) ou a remove se o vínculo acabou (spec 0009)."""
    instagram = page.get("instagram")
    stale = SocialAccount.objects.filter(
        owner=user, platform=SocialAccount.Platform.INSTAGRAM, parent=page_account
    )
    if not instagram:
        stale.delete()
        return
    stale.exclude(external_id=instagram["id"]).delete()  # a Página passou a ter outro Instagram
    SocialAccount.objects.update_or_create(
        owner=user,
        platform=SocialAccount.Platform.INSTAGRAM,
        external_id=instagram["id"],
        defaults={
            "name": instagram["username"] or instagram["name"] or instagram["id"],
            "username": instagram["username"],
            "category": "",
            "picture_url": instagram["picture_url"] if len(instagram["picture_url"]) <= 500 else "",
            "granted_tasks": page["tasks"],
            "access_token_enc": page["token_enc"],  # o mesmo token (já cifrado) da Página
            "parent": page_account,
            "status": SocialAccount.Status.ACTIVE,
            "last_error": "",
        },
    )
