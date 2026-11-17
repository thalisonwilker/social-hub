"""Cliente fino da Graph API da Meta (camada anticorrupção). Ver ADR-0003.

Regras de segurança (AC-16):
- client_secret e code trafegam em POST (corpo); tokens vão no header Authorization.
- Nenhuma URL com credencial; nenhum corpo de resposta é exposto ou logado.
"""
import logging
from urllib.parse import urlencode

import requests
from django.conf import settings

logger = logging.getLogger("apps.social.meta")

GRAPH_BASE = "https://graph.facebook.com"
DIALOG_BASE = "https://www.facebook.com"
TOKEN_ERROR_CODES = {102, 190}  # sessão/token inválido, expirado ou revogado
MAX_PAGES = 10  # limite de páginas de resultado ao listar /me/accounts


class MetaApiError(Exception):
    """Erro da Graph API ou de rede, já sanitizado (sem corpo de resposta nem credenciais)."""

    def __init__(self, message, *, code=None, subcode=None, status=None, endpoint=""):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.status = status
        self.endpoint = endpoint

    @property
    def is_token_error(self) -> bool:
        return self.code in TOKEN_ERROR_CODES or self.status == 401


class BaseGraphClient:
    """Base comum dos clientes Graph (Facebook e Threads): requisição sanitizada, sem logar URL nem parâmetros."""

    base_url = ""  # definido pela subclasse (ex.: https://graph.facebook.com)

    def __init__(self, *, version, timeout=10, upload_timeout=30, session=None):
        self.version = version
        self.timeout = timeout
        self.upload_timeout = upload_timeout
        self.session = session or requests.Session()

    @staticmethod
    def _require_token(data: dict, endpoint: str) -> str:
        token = data.get("access_token")
        if not token:
            logger.warning("graph_error endpoint=%s code=%s subcode=%s", endpoint, "no_token", None)
            raise MetaApiError("Resposta da Meta sem token.", endpoint=endpoint)
        return token

    def _request(self, method, path, *, params=None, data=None, files=None, token=None, timeout=None, versioned=True) -> dict:
        """`token` vai no header Authorization (Facebook). `versioned=False` omite a versão do caminho (ex.: oauth do Threads).

        Credenciais exigidas pela API no corpo/consulta são passadas pelo chamador em `data`/`params`; este método
        nunca registra URL, parâmetros nem corpo de resposta.
        """
        prefix = f"{self.base_url}/{self.version}" if versioned else self.base_url
        url = f"{prefix}/{path}"
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            response = self.session.request(
                method, url, params=params, data=data, files=files, headers=headers, timeout=timeout or self.timeout
            )
        except requests.RequestException:
            logger.warning("graph_error endpoint=%s code=%s subcode=%s", path, "network", None)
            raise MetaApiError("Falha de rede ao falar com a Meta.", code="network", endpoint=path) from None

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            logger.warning("graph_error endpoint=%s code=%s subcode=%s", path, "bad_response", None)
            raise MetaApiError(
                "Resposta inválida da Meta.", code="bad_response", status=response.status_code, endpoint=path
            )

        error = payload.get("error")
        if response.status_code >= 400 or error:
            # Formatos: {"error": {"code": ..}} (Graph) ou {"error_type": .., "code": ..} (OAuth do Threads).
            source = error if isinstance(error, dict) else payload
            code, subcode = source.get("code"), source.get("error_subcode")
            logger.warning("graph_error endpoint=%s code=%s subcode=%s", path, code, subcode)
            raise MetaApiError(
                "A Meta recusou a requisição.",
                code=code,
                subcode=subcode,
                status=response.status_code,
                endpoint=path,
            )
        return payload


class GraphClient(BaseGraphClient):
    base_url = GRAPH_BASE

    def __init__(self, *, app_id, app_secret, config_id, redirect_uri, version, timeout=10, upload_timeout=30, session=None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.config_id = config_id
        self.redirect_uri = redirect_uri
        super().__init__(version=version, timeout=timeout, upload_timeout=upload_timeout, session=session)

    @classmethod
    def from_settings(cls):
        return cls(
            app_id=settings.META_APP_ID,
            app_secret=settings.META_APP_SECRET,
            config_id=settings.META_LOGIN_CONFIG_ID,
            redirect_uri=settings.META_REDIRECT_URI,
            version=settings.META_GRAPH_VERSION,
            timeout=settings.META_HTTP_TIMEOUT,
            upload_timeout=settings.META_UPLOAD_TIMEOUT,
        )

    # --- OAuth -----------------------------------------------------------------
    def login_url(self, state: str) -> str:
        query = urlencode(
            {
                "client_id": self.app_id,
                "config_id": self.config_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "override_default_response_type": "true",
                "state": state,
            }
        )
        return f"{DIALOG_BASE}/{self.version}/dialog/oauth?{query}"

    def exchange_code(self, code: str) -> str:
        """Troca o `code` pelo token de usuário (POST: code e secret fora da URL)."""
        data = self._request(
            "POST",
            "oauth/access_token",
            data={
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "redirect_uri": self.redirect_uri,
                "code": code,
            },
        )
        return self._require_token(data, "oauth/access_token")

    def extend_token(self, short_lived_token: str) -> str:
        """Troca o token de usuário por um de longa duração."""
        data = self._request(
            "POST",
            "oauth/access_token",
            data={
                "grant_type": "fb_exchange_token",
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "fb_exchange_token": short_lived_token,
            },
        )
        return self._require_token(data, "oauth/access_token")

    # --- Páginas ---------------------------------------------------------------
    def list_pages(self, user_token: str) -> list[dict]:
        """Páginas administradas pelo usuário, com o token de cada uma (`/me/accounts`)."""
        pages: list[dict] = []
        after = None
        for _ in range(MAX_PAGES):
            params = {"fields": "id,name,category,picture{url},access_token,tasks", "limit": 100}
            if after:
                params["after"] = after
            data = self._request("GET", "me/accounts", params=params, token=user_token)
            for item in data.get("data", []):
                pages.append(
                    {
                        "id": str(item.get("id", "")),
                        "name": item.get("name", ""),
                        "category": item.get("category", ""),
                        "picture_url": ((item.get("picture") or {}).get("data") or {}).get("url", ""),
                        "access_token": item.get("access_token") or None,
                        "tasks": item.get("tasks") or [],
                    }
                )
            paging = data.get("paging") or {}
            # Não seguimos `paging.next`: a URL carrega o access_token. Usamos só o cursor.
            after = (paging.get("cursors") or {}).get("after") if paging.get("next") else None
            if not after:
                break
        return [p for p in pages if p["id"]]

    def get_page(self, page_id: str, page_token: str) -> dict:
        return self._request("GET", page_id, params={"fields": "id,name"}, token=page_token)

    # --- Publicação ------------------------------------------------------------
    def publish_photo(self, page_id: str, page_token: str, *, image, filename: str, content_type: str, message: str) -> dict:
        """Publica uma foto com legenda na Página (`POST /{page_id}/photos`, multipart).

        O arquivo vai no corpo (nunca por URL pública). Devolve {"photo_id", "post_id"}.
        """
        data = self._request(
            "POST",
            f"{page_id}/photos",
            data={"message": message, "published": "true"},
            files={"source": (filename, image, content_type)},
            token=page_token,
            timeout=self.upload_timeout,
        )
        post_id = data.get("post_id") or data.get("id")
        if not post_id:
            logger.warning("graph_error endpoint=%s code=%s subcode=%s", "photos", "no_post_id", None)
            raise MetaApiError("Resposta da Meta sem identificador do post.", code="bad_response", endpoint="photos")
        return {"photo_id": data.get("id", ""), "post_id": str(post_id)}
