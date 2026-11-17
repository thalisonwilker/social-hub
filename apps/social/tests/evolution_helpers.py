from contextlib import contextmanager
from unittest import mock

from apps.social.models import SocialAccount
from apps.social.services.evolution import EvolutionApiError, EvolutionClient

from .helpers import KEY

EVO_HOST = "evo.exemplo.host"
INSTANCE_KEY = "chave-da-instancia-SECRETA-123"

EVOLUTION_SETTINGS = {
    "EVOLUTION_API_URL": f"https://{EVO_HOST}",
    "EVOLUTION_TIMEOUT_SECONDS": 60,
    "META_TOKEN_ENCRYPTION_KEY": KEY,
}


def make_whatsapp_account(owner, instance="loja", *, status=SocialAccount.Status.ACTIVE, key="chave-da-loja", name=None):
    account = SocialAccount(
        owner=owner,
        platform=SocialAccount.Platform.WHATSAPP_STATUS,
        external_id=instance,
        name=name or instance,
        status=status,
    )
    account.set_token(key)
    account.save()
    return account


@contextmanager
def evolution_state(state="open", *, error_code=None, error_status=None):
    """Patch de EvolutionClient.connection_state (sem rede). `error_code` faz levantar EvolutionApiError."""
    side_effect = EvolutionApiError("erro", code=error_code, status=error_status) if error_code else None
    with mock.patch.object(EvolutionClient, "connection_state", return_value=state, side_effect=side_effect) as m:
        yield m
