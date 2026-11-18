"""Cliente fino do DeepSeek para gerar texto (API compatível com a da OpenAI). Ver specs/0008-gerar-imagem-com-ia (AC-9).

Mesmas garantias do cliente do Gemini: host fixo, chave só no header `Authorization` (nunca na URL), prompt/chave/corpo nunca em log.
"""
import logging

import requests
from django.conf import settings

from . import gemini
from .gemini import GeminiError
from .transport import classify_request_error

logger = logging.getLogger("apps.social.meta")

LABEL = "DeepSeek"
CHAT_URL = "https://api.deepseek.com/chat/completions"
MODELS_URL = "https://api.deepseek.com/models"


def _error(code, detail=""):
    return GeminiError(code, detail, label=LABEL)


def _headers(api_key):
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _fail(response, api_key, what):
    code = gemini._code_for_status(response)
    logger.warning("deepseek %s failed status=%s code=%s", what, response.status_code, code)
    detail = gemini._detail(response, api_key) if response.status_code in (400, 402, 403, 404, 422, 429) else ""
    return _error(code, detail)


def check_key(api_key: str, *, session=None) -> None:
    """Testa a chave listando os modelos (não gera texto, não gasta saldo)."""
    if not api_key:
        raise _error("no_key")
    http = session or requests
    try:
        response = http.get(MODELS_URL, headers=_headers(api_key), timeout=20)
    except requests.RequestException as exc:
        code = classify_request_error(exc)
        logger.warning("deepseek key check failed code=%s", code)
        raise _error("timeout" if code == "timeout" else "network") from None
    if response.status_code != 200:
        raise _fail(response, api_key, "key check")


def generate_text(api_key: str, model: str, prompt: str, *, session=None) -> str:
    if not api_key:
        raise _error("no_key")
    if not model or not gemini._MODEL_RE.match(model):
        raise _error("invalid_model")
    http = session or requests
    try:
        response = http.post(
            CHAT_URL,
            headers=_headers(api_key),
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": gemini.TEXT_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
            timeout=min(settings.GEMINI_TIMEOUT_SECONDS, 60),
        )
    except requests.RequestException as exc:
        code = classify_request_error(exc)
        logger.warning("deepseek text failed model=%s code=%s", model, code)
        raise _error("timeout" if code == "timeout" else "network") from None
    if response.status_code != 200:
        raise _fail(response, api_key, "text")
    try:
        text = (response.json()["choices"][0]["message"].get("content") or "").strip()
    except (ValueError, KeyError, IndexError, AttributeError, TypeError):
        logger.warning("deepseek text invalid response model=%s", model)
        raise _error("bad_response") from None
    if not text:
        raise _error("blocked_text")
    return text
