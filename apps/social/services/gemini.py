"""Cliente fino do Google Gemini para gerar imagem (camada anticorrupção). Ver specs/0008-gerar-imagem-com-ia.

Segurança: host fixo (nunca informado pelo usuário); chave só no header `x-goog-api-key` (nunca na URL); o modelo é validado
contra `GEMINI_IMAGE_MODELS`; prompt, chave e corpo de resposta nunca entram em log nem em mensagem de erro.
"""
import base64
import binascii
import logging
import re

import requests
from django.conf import settings

from .transport import classify_request_error

logger = logging.getLogger("apps.social.meta")

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
MAX_RESPONSE_BYTES = 20 * 1024 * 1024

MESSAGES = {
    "no_key": "Cadastre uma chave de API do Gemini para gerar conteúdo com IA.",
    "invalid_model": "Modelo de imagem inválido.",
    "auth": "A chave de API do Gemini foi recusada. Confira a chave cadastrada.",
    "quota": "Limite de uso do Gemini atingido. Tente mais tarde ou confira sua cota.",
    "blocked": "O Gemini não gerou a imagem para este prompt (conteúdo bloqueado ou sem imagem). Reescreva o prompt.",
    "timeout": "O Gemini demorou demais para responder. Tente novamente.",
    "network": "Não foi possível falar com o Gemini. Tente novamente.",
    "blocked_text": "O Gemini não gerou texto para este prompt. Reescreva o prompt.",
    "balance": "Saldo insuficiente na conta do Gemini. Adicione créditos e tente de novo.",
    "bad_response": "Resposta inesperada do Gemini. Tente novamente.",
    "rejected": "O Gemini recusou o pedido. Confira o modelo e o prompt.",
    "server": "O Gemini está com problemas no momento. Tente novamente.",
}
_MODEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


class GeminiError(Exception):
    """Erro já sanitizado: `code` é uma chave de MESSAGES; a mensagem é própria para exibir ao usuário."""

    def __init__(self, code, detail="", label="Gemini"):
        text = MESSAGES[code].replace("Gemini", label)
        super().__init__(text + (f" Detalhe do provedor: {detail}" if detail else ""))
        self.code = code
        self.detail = detail


def _detail(response, api_key) -> str:
    """Mensagem de erro do Google (curta, sem a chave) para diagnóstico: ex. cota zero, faturamento, modelo inexistente."""
    try:
        error = (response.json() or {}).get("error") or {}
        text = f"{error.get('status', '')}: {error.get('message', '')}".strip(": ")
    except (ValueError, AttributeError, TypeError):
        return ""
    text = " ".join(text.split())
    if api_key:
        text = text.replace(api_key, "[chave]")
    return text[:220]


def allowed_models() -> list[str]:
    return [m for m in settings.GEMINI_IMAGE_MODELS if _MODEL_RE.match(m)]


def _code_for_status(response) -> str:
    status = response.status_code
    if status == 400:  # chave inválida também vem como 400 (API_KEY_INVALID) — sem ler o corpo além do necessário
        return "auth" if "API_KEY_INVALID" in response.text[:2000] else "rejected"
    if status == 402:  # DeepSeek: saldo insuficiente
        return "balance"
    return "auth" if status in (401, 403) else "quota" if status == 429 else "server" if status >= 500 else "rejected"


def check_key(api_key: str, *, session=None) -> None:
    """Testa a chave listando 1 modelo (não gera imagem, não consome cota de geração). Levanta GeminiError."""
    if not api_key:
        raise GeminiError("no_key")
    http = session or requests
    try:
        response = http.get(
            MODELS_URL, headers={"x-goog-api-key": api_key}, params={"pageSize": 1}, timeout=min(settings.GEMINI_TIMEOUT_SECONDS, 20)
        )
    except requests.RequestException as exc:
        code = classify_request_error(exc)
        logger.warning("gemini key check failed code=%s", code)
        raise GeminiError("timeout" if code == "timeout" else "network") from None
    if response.status_code != 200:
        code = _code_for_status(response)
        logger.warning("gemini key check failed status=%s code=%s", response.status_code, code)
        raise GeminiError(code, _detail(response, api_key) if response.status_code in (400, 403, 404, 429) else "")


def generate_image(api_key: str, model: str, prompt: str, *, session=None) -> tuple[bytes, str]:
    """Gera uma imagem. Devolve (bytes, content_type). Levanta GeminiError."""
    if not api_key:
        raise GeminiError("no_key")
    if model not in allowed_models():
        raise GeminiError("invalid_model")
    http = session or requests
    try:
        response = http.post(
            BASE_URL.format(model=model),
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
            },
            timeout=settings.GEMINI_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        code = classify_request_error(exc)
        logger.warning("gemini generate failed model=%s code=%s", model, code)
        raise GeminiError("timeout" if code == "timeout" else "network") from None

    status = response.status_code
    if status != 200:
        code = _code_for_status(response)
        logger.warning("gemini generate failed model=%s status=%s code=%s", model, status, code)
        raise GeminiError(code, _detail(response, api_key) if status in (400, 403, 404, 429) else "")
    try:
        payload = response.json()
    except ValueError:
        logger.warning("gemini generate invalid json model=%s", model)
        raise GeminiError("bad_response") from None
    return _extract_image(payload, model)


def _extract_image(payload, model):
    try:
        candidates = payload.get("candidates") or []
        for candidate in candidates:
            for part in (candidate.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    data = base64.b64decode(inline["data"], validate=True)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise GeminiError("bad_response")
                    return data, inline.get("mimeType") or inline.get("mime_type") or "image/png"
    except (AttributeError, TypeError, binascii.Error, ValueError):
        raise GeminiError("bad_response") from None
    logger.warning("gemini generate without image model=%s", model)
    raise GeminiError("blocked")


TEXT_SYSTEM_PROMPT = (
    "Você escreve textos para publicações em redes sociais, em português do Brasil. "
    "Responda SOMENTE com o texto final da publicação, em texto simples (sem markdown, sem títulos, sem aspas, "
    "sem explicações), com no máximo 450 caracteres."
)


def generate_text(api_key: str, model: str, prompt: str, *, session=None) -> str:
    """Gera o texto da publicação. Levanta GeminiError."""
    if not api_key:
        raise GeminiError("no_key")
    if not model or not _MODEL_RE.match(model):
        raise GeminiError("invalid_model")
    http = session or requests
    try:
        response = http.post(
            BASE_URL.format(model=model),
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": TEXT_SYSTEM_PROMPT}]},
                "contents": [{"parts": [{"text": prompt}]}],
            },
            timeout=min(settings.GEMINI_TIMEOUT_SECONDS, 60),
        )
    except requests.RequestException as exc:
        code = classify_request_error(exc)
        logger.warning("gemini text failed model=%s code=%s", model, code)
        raise GeminiError("timeout" if code == "timeout" else "network") from None
    if response.status_code != 200:
        code = _code_for_status(response)
        logger.warning("gemini text failed model=%s status=%s code=%s", model, response.status_code, code)
        raise GeminiError(code, _detail(response, api_key) if response.status_code in (400, 403, 404, 429) else "")
    try:
        payload = response.json()
        parts = [
            part.get("text", "")
            for candidate in (payload.get("candidates") or [])[:1]
            for part in (candidate.get("content") or {}).get("parts") or []
            if not part.get("thought")
        ]
    except (ValueError, AttributeError, TypeError):
        logger.warning("gemini text invalid response model=%s", model)
        raise GeminiError("bad_response") from None
    text = "".join(parts).strip()
    if not text:
        raise GeminiError("blocked_text")
    return text
