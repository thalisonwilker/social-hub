"""Cliente fino da Threads API (camada anticorrupção). Ver ADR-0006.

Segue a documentação oficial: login em threads.com, API em graph.threads.com.
- `client_secret` e `code` vão em POST (corpo).
- Onde a Meta documenta GET com token na consulta (troca, renovação, perfil, status, permalink), o token vai em `params`;
  nos POSTs de container/publicação ele vai no corpo. Nada disso é registrado em log (ver BaseGraphClient).
"""
import logging
from urllib.parse import urlencode

from django.conf import settings

from .meta import BaseGraphClient, MetaApiError

logger = logging.getLogger("apps.social.meta")

AUTH_URL = "https://threads.com/oauth/authorize"
THREADS_BASE = "https://graph.threads.com"
SCOPES = "threads_basic,threads_content_publish,threads_delete"  # threads_delete: apagar posts (spec 0010)


class ThreadsClient(BaseGraphClient):
    base_url = THREADS_BASE

    def __init__(self, *, app_id, app_secret, redirect_uri, version="v1.0", timeout=10, session=None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri
        super().__init__(version=version, timeout=timeout, session=session)

    @classmethod
    def from_settings(cls):
        return cls(
            app_id=settings.THREADS_APP_ID,
            app_secret=settings.THREADS_APP_SECRET,
            redirect_uri=settings.THREADS_REDIRECT_URI,
            version=settings.THREADS_GRAPH_VERSION,
            timeout=settings.META_HTTP_TIMEOUT,
        )

    # --- OAuth / tokens --------------------------------------------------------
    def login_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": self.app_id,
                "redirect_uri": self.redirect_uri,
                "scope": SCOPES,
                "response_type": "code",
                "state": state,
            }
        )
        return f"{AUTH_URL}?{query}"

    def exchange_code(self, code: str) -> dict:
        """Troca o `code` pelo token curto (1 h) e o `user_id`. POST: code e secret no corpo."""
        data = self._request(
            "POST",
            "oauth/access_token",
            data={
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self.redirect_uri,
            },
            versioned=False,
        )
        token = self._require_token(data, "oauth/access_token")
        user_id = data.get("user_id")
        if not user_id:
            logger.warning("graph_error endpoint=%s code=%s subcode=%s", "oauth/access_token", "no_user_id", None)
            raise MetaApiError("Resposta do Threads sem user_id.", code="bad_response", endpoint="oauth/access_token")
        return {"access_token": token, "user_id": str(user_id)}

    def extend_token(self, short_lived_token: str) -> dict:
        """Token curto → token de 60 dias (`th_exchange_token`, documentado como GET)."""
        data = self._request(
            "GET",
            "access_token",
            params={"grant_type": "th_exchange_token", "client_secret": self.app_secret, "access_token": short_lived_token},
            versioned=False,
        )
        return self._token_with_expiry(data, "access_token")

    def refresh_token(self, long_lived_token: str) -> dict:
        """Renova o token de 60 dias (`th_refresh_token`, documentado como GET)."""
        data = self._request(
            "GET",
            "refresh_access_token",
            params={"grant_type": "th_refresh_token", "access_token": long_lived_token},
            versioned=False,
        )
        return self._token_with_expiry(data, "refresh_access_token")

    def _token_with_expiry(self, data: dict, endpoint: str) -> dict:
        token = self._require_token(data, endpoint)
        try:
            expires_in = int(data["expires_in"])
        except (KeyError, TypeError, ValueError):
            logger.warning("graph_error endpoint=%s code=%s subcode=%s", endpoint, "no_expires_in", None)
            raise MetaApiError("Resposta do Threads sem validade do token.", code="bad_response", endpoint=endpoint) from None
        return {"access_token": token, "expires_in": expires_in}

    # --- Perfil ----------------------------------------------------------------
    def get_profile(self, user_id: str, token: str) -> dict:
        data = self._request(
            "GET",
            user_id,
            params={"fields": "id,username,name,threads_profile_picture_url", "access_token": token},
        )
        return {
            "id": str(data.get("id", user_id)),
            "username": data.get("username", ""),
            "name": data.get("name", ""),
            "picture_url": data.get("threads_profile_picture_url", ""),
        }

    # --- Publicação de texto ---------------------------------------------------
    def create_text_container(self, user_id: str, token: str, text: str) -> str:
        data = self._request(
            "POST",
            f"{user_id}/threads",
            data={"media_type": "TEXT", "text": text, "access_token": token},
        )
        return self._require_id(data, f"{user_id}/threads")

    def create_image_container(self, user_id: str, token: str, text: str, image_url: str) -> str:
        """Container IMAGE: a Meta baixa a imagem de `image_url` (URL pública assinada do Hub, spec 0005).

        Tudo no corpo do POST (inclusive a URL com o token da imagem); nada disso é registrado em log.
        """
        data = self._request(
            "POST",
            f"{user_id}/threads",
            data={"media_type": "IMAGE", "image_url": image_url, "text": text, "access_token": token},
        )
        return self._require_id(data, f"{user_id}/threads")

    def container_status(self, container_id: str, token: str) -> dict:
        data = self._request(
            "GET", container_id, params={"fields": "status,error_message", "access_token": token}
        )
        return {"status": data.get("status", ""), "error_message": data.get("error_message", "")}

    def publish_container(self, user_id: str, token: str, container_id: str) -> str:
        data = self._request(
            "POST",
            f"{user_id}/threads_publish",
            data={"creation_id": container_id, "access_token": token},
            effect=True,  # chamada que cria o post: sem resposta = resultado desconhecido (spec 0007)
        )
        return self._require_id(data, f"{user_id}/threads_publish", effect=True)

    def get_permalink(self, media_id: str, token: str) -> str:
        data = self._request("GET", media_id, params={"fields": "permalink", "access_token": token})
        return data.get("permalink", "") or ""

    def delete_media(self, media_id: str, token: str) -> bool:
        """Apaga um post do Threads (`DELETE /{media_id}`; exige `threads_delete`; 100/dia). `{"success": true}` ou erro.

        O token vai em `params` como na documentação (nunca é registrado em log). Chamada com efeito.
        """
        data = self._request("DELETE", media_id, params={"access_token": token}, effect=True, label="delete")
        if data.get("success") is not True:
            logger.warning("graph_error endpoint=%s code=%s subcode=%s", "delete", "bad_response", None)
            raise MetaApiError("Resposta do Threads sem confirmação.", code="bad_response", endpoint="delete", outcome_unknown=True)
        return True

    @staticmethod
    def _require_id(data: dict, endpoint: str, *, effect: bool = False) -> str:
        value = data.get("id")
        if not value:
            logger.warning("graph_error endpoint=%s code=%s subcode=%s", endpoint, "no_id", None)
            raise MetaApiError(
                "Resposta do Threads sem identificador.", code="bad_response", endpoint=endpoint, outcome_unknown=effect
            )
        return str(value)
