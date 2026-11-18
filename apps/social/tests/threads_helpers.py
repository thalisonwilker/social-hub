from datetime import timedelta
from unittest import mock

from django.utils import timezone

from apps.social.models import SocialAccount
from apps.social.services.threads import ThreadsClient

from .helpers import KEY

HOST = "hub-teste.trycloudflare.com"
SHORT = "short-token-111"
LONG = "long-token-222"
SECRET = "threads-secret-ZZZ"
CODE = "auth-code-333"

THREADS_SETTINGS = {
    "THREADS_APP_ID": "1602810271151684",
    "THREADS_APP_SECRET": SECRET,
    "THREADS_REDIRECT_URI": f"https://{HOST}/contas/threads/callback/",
    "THREADS_GRAPH_VERSION": "v1.0",
    "THREADS_REFRESH_WINDOW_DAYS": 30,
    "THREADS_CONTAINER_WAIT_SECONDS": 20,
    "PUBLIC_BASE_URL": "",  # hermético: não depende do .env do desenvolvedor (túnel)
    "META_TOKEN_ENCRYPTION_KEY": KEY,
    "ALLOWED_HOSTS": [HOST, "testserver", "localhost"],
}

PROFILE = {"id": "900", "username": "maria", "name": "Maria", "picture_url": "https://img/maria.jpg"}


class threads_api:
    """Patches de ThreadsClient (sem rede): troca de code, token longo e perfil."""

    def __init__(self, *, exchange=None, extend=None, profile=None, exchange_error=None, extend_error=None, profile_error=None):
        self.exchange = exchange or {"access_token": SHORT, "user_id": "900"}
        self.extend = extend or {"access_token": LONG, "expires_in": 5183944}
        self.profile = profile or PROFILE
        self.errors = (exchange_error, extend_error, profile_error)
        self.patches = []

    def __enter__(self):
        e, x, p = self.errors
        specs = [
            ("exchange_code", {"return_value": self.exchange, "side_effect": e}),
            ("extend_token", {"return_value": self.extend, "side_effect": x}),
            ("get_profile", {"return_value": self.profile, "side_effect": p}),
        ]
        self.mocks = {}
        for name, kwargs in specs:
            patcher = mock.patch.object(ThreadsClient, name, **kwargs)
            self.mocks[name] = patcher.start()
            self.patches.append(patcher)
        return self.mocks

    def __exit__(self, *exc):
        for patcher in self.patches:
            patcher.stop()


def make_threads_account(owner, external_id="900", *, days_left=60, refreshed_hours_ago=48, status=SocialAccount.Status.ACTIVE,
                         username="maria", token="threads-long-token"):
    now = timezone.now()
    account = SocialAccount(
        owner=owner, platform=SocialAccount.Platform.THREADS, external_id=external_id, name=username.title(),
        username=username, status=status,
        token_expires_at=now + timedelta(days=days_left), token_refreshed_at=now - timedelta(hours=refreshed_hours_ago),
    )
    account.set_token(token)
    account.save()
    return account
