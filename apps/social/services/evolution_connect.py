"""Cadastro e verificação de instâncias da Evolution (spec 0006): sem OAuth, só nome da instância + chave.

Nada daqui registra a chave nem o nome da instância (AC-14).
"""
import logging

from django.utils import timezone

from apps.social.models import SocialAccount

from .evolution import EvolutionApiError, EvolutionClient

logger = logging.getLogger("apps.social.meta")

PLATFORM = SocialAccount.Platform.WHATSAPP_STATUS

MSG_NOT_CONFIGURED = "Integração com o WhatsApp não configurada."
MSG_NOT_OPEN = "O número não está conectado na Evolution. Faça o pareamento por lá e tente de novo."
MSG_KEY_REFUSED = "Chave recusada pela Evolution. Confira a chave da instância."
MSG_NOT_FOUND = "Instância não encontrada na Evolution."
MSG_UNREACHABLE = "Não foi possível falar com a Evolution. Tente novamente em instantes."
LAST_ERROR_REAUTH = "Evolution: instância desconectada ou chave recusada"

OPEN = "open"
REAUTH_CODES = {"auth", "not_found"}


class RegistrationError(Exception):
    """Erro de cadastro já com mensagem amigável para o usuário."""


def register_instance(owner, instance: str, key: str, label: str = "", *, client: EvolutionClient) -> tuple[SocialAccount, bool]:
    """Valida a conexão (`open`) e grava/atualiza a conta. Devolve (conta, criada). Nada é gravado em caso de erro."""
    try:
        state = client.connection_state(instance, key)
    except EvolutionApiError as exc:
        raise RegistrationError(_message_for(exc.code)) from None
    if state != OPEN:
        raise RegistrationError(MSG_NOT_OPEN)

    account = SocialAccount.objects.filter(owner=owner, platform=PLATFORM, external_id=instance).first()
    created = account is None
    if created:
        account = SocialAccount(owner=owner, platform=PLATFORM, external_id=instance, name=label or instance)
    elif label:
        account.name = label
    account.set_token(key)
    account.status = SocialAccount.Status.ACTIVE
    account.last_error = ""
    account.token_expires_at = None
    account.last_checked_at = timezone.now()
    account.save()
    logger.info("whatsapp_account_registered created=%d", int(created))
    return account, created


def _message_for(code: str) -> str:
    if code == "auth":
        return MSG_KEY_REFUSED
    if code == "not_found":
        return MSG_NOT_FOUND
    return MSG_UNREACHABLE


def needs_reauth(account: SocialAccount) -> None:
    """Marca a conta como Reconexão necessária (instância desconectada, chave recusada ou inexistente)."""
    SocialAccount.objects.filter(pk=account.pk).update(
        status=SocialAccount.Status.NEEDS_REAUTH, last_error=LAST_ERROR_REAUTH, last_checked_at=timezone.now()
    )
