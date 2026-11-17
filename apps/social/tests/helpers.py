from unittest import mock

from cryptography.fernet import Fernet

from apps.social.services.meta import GraphClient, MetaApiError

KEY = Fernet.generate_key().decode()
SECRET = "app-secret-XYZ"
USER_TOKEN = "user-token-ABC"
PAGE_TOKEN_1 = "page-token-ONE"
PAGE_TOKEN_2 = "page-token-TWO"

VALID_META_SETTINGS = {
    "META_APP_ID": "123",
    "META_APP_SECRET": SECRET,
    "META_LOGIN_CONFIG_ID": "456",
    "META_REDIRECT_URI": "http://localhost:8080/contas/facebook/callback/",
    "META_GRAPH_VERSION": "v27.0",
    "META_TOKEN_ENCRYPTION_KEY": KEY,
}

PAGES = [
    {"id": "1", "name": "Loja <b>Central</b>", "category": "Varejo", "picture_url": "",
     "access_token": PAGE_TOKEN_1, "tasks": ["CREATE_CONTENT"]},
    {"id": "2", "name": "Café ☕", "category": "Restaurante", "picture_url": "",
     "access_token": PAGE_TOKEN_2, "tasks": []},
]


def patch_graph(pages=None, *, error=None):
    """Patches de GraphClient: troca de code/token e lista de Páginas (sem rede)."""
    stack = [
        mock.patch.object(GraphClient, "exchange_code", side_effect=error, return_value="short"),
        mock.patch.object(GraphClient, "extend_token", return_value=USER_TOKEN),
        mock.patch.object(
            GraphClient, "list_pages", return_value=[dict(p) for p in (PAGES if pages is None else pages)]
        ),
    ]
    return stack


class graph_patches:
    """Context manager que aplica os patches acima."""

    def __init__(self, pages=None, error: MetaApiError | None = None):
        self.patches = patch_graph(pages, error=error)

    def __enter__(self):
        return [p.start() for p in self.patches]

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()
