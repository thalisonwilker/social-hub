"""Cliente fino da Evolution API (camada anticorrupção). Ver design da spec 0006.

Segurança (AC-14):
- O host vem SEMPRE da configuração do servidor (`EVOLUTION_API_URL`, só a origem HTTPS); o usuário informa apenas o nome da instância,
  validado e, por construção, sem caracteres que alterem a rota.
- A chave da instância vai só no header `apikey`; texto, base64 e chave nunca entram na URL nem em log. O log traz só rótulo do endpoint, status e código curto.

CONTRATO NÃO CONFIRMADO (design, "Questões em aberto"): o corpo do Status, o formato do base64 e a resposta do estado da conexão
variam por versão da Evolution e a documentação oficial não pôde ser lida. Tudo o que depende disso fica concentrado em `_status_body`,
`_extract_message_id` e `_extract_state`; a task 10 (UAT) fixa esses pontos lendo a instância real.
"""
import base64
import logging

import requests

from apps.social import conf
from apps.social.validators import is_valid_instance_name

logger = logging.getLogger("apps.social.meta")

STATUS_PATH = "message/sendStatus/{instance}"
STATE_PATH = "instance/connectionState/{instance}"


class EvolutionApiError(Exception):
    """Erro da Evolution ou de rede, já sanitizado (sem corpo de resposta, chave ou conteúdo).

    `code`: not_configured, invalid_instance, auth, not_found, rate_limit, rejected, server, timeout, network, bad_response.
    """

    def __init__(self, message, *, code, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


def _code_for_status(status: int) -> str:
    if status in (401, 403):
        return "auth"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limit"
    if status >= 500:
        return "server"
    return "rejected"


class EvolutionClient:
    def __init__(self, *, base_url, timeout=60, session=None):
        self.base_url = base_url
        self.timeout = timeout
        self.session = session or requests.Session()

    @classmethod
    def from_settings(cls):
        from django.conf import settings

        base_url = conf.evolution_base_url()
        if not base_url:
            raise EvolutionApiError("Integração com a Evolution não configurada.", code="not_configured")
        return cls(base_url=base_url, timeout=settings.EVOLUTION_TIMEOUT_SECONDS)

    # --- operações ---------------------------------------------------------------
    def connection_state(self, instance: str, key: str, *, timeout=None) -> str:
        """Estado da conexão da instância em minúsculas (`open`, `close`, `connecting`...)."""
        payload = self._request("GET", STATE_PATH, "connectionState", instance, key, timeout=timeout)
        return self._extract_state(payload)

    def send_status_text(self, instance: str, key: str, text: str, *, timeout=None) -> str:
        """Publica um Status de texto para todos os contatos. Devolve o id da mensagem (ou "")."""
        body = self._status_body("text", content=text)
        return self._extract_message_id(self._request("POST", STATUS_PATH, "sendStatus", instance, key, body=body, timeout=timeout))

    def send_status_image(self, instance: str, key: str, image: bytes, text: str, *, timeout=None) -> str:
        """Publica um Status de imagem (base64, sem URL pública) com `text` como legenda. Devolve o id (ou "")."""
        body = self._status_body("image", content=base64.b64encode(image).decode("ascii"), caption=text)
        return self._extract_message_id(self._request("POST", STATUS_PATH, "sendStatus", instance, key, body=body, timeout=timeout))

    # --- contrato (a confirmar no UAT) ---------------------------------------------
    @staticmethod
    def _status_body(kind: str, *, content: str, caption: str = "") -> dict:
        body = {"type": kind, "content": content, "allContacts": True}
        if caption:
            body["caption"] = caption
        return body

    @staticmethod
    def _extract_message_id(payload: dict) -> str:
        key = payload.get("key")
        value = key.get("id") if isinstance(key, dict) else None
        return str(value) if value else ""

    @staticmethod
    def _extract_state(payload: dict) -> str:
        nested = payload.get("instance")
        state = nested.get("state") if isinstance(nested, dict) else None
        state = state or payload.get("state")
        if not isinstance(state, str) or not state:
            logger.warning("evolution_error endpoint=%s status=%s code=%s", "connectionState", None, "bad_response")
            raise EvolutionApiError("Resposta da Evolution sem estado da conexão.", code="bad_response")
        return state.lower()

    # --- transporte ------------------------------------------------------------------
    def _request(self, method, path_template, label, instance, key, *, body=None, timeout=None) -> dict:
        if not is_valid_instance_name(instance):
            raise EvolutionApiError("Nome de instância inválido.", code="invalid_instance")
        url = f"{self.base_url}/{path_template.format(instance=instance)}"
        try:
            response = self.session.request(
                method, url, json=body, headers={"apikey": key}, timeout=timeout or self.timeout
            )
        except requests.Timeout:
            self._log(label, None, "timeout")
            raise EvolutionApiError("Tempo esgotado ao falar com a Evolution.", code="timeout") from None
        except requests.RequestException:
            self._log(label, None, "network")
            raise EvolutionApiError("Falha de rede ao falar com a Evolution.", code="network") from None

        status = response.status_code
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if status >= 400:
            code = _code_for_status(status)
            self._log(label, status, code)
            raise EvolutionApiError("A Evolution recusou a requisição.", code=code, status=status)
        if not isinstance(payload, dict):
            self._log(label, status, "bad_response")
            raise EvolutionApiError("Resposta inválida da Evolution.", code="bad_response", status=status)
        if payload.get("error"):
            self._log(label, status, "rejected")
            raise EvolutionApiError("A Evolution recusou a requisição.", code="rejected", status=status)
        return payload

    @staticmethod
    def _log(label, status, code):
        logger.warning("evolution_error endpoint=%s status=%s code=%s", label, status, code)
