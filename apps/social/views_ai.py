"""Gerar imagem com IA (Google Gemini) na nova publicação. Ver specs/0008-gerar-imagem-com-ia.

Tudo é do próprio usuário (login + CSRF do middleware); a chave nunca é devolvida; erros saem sanitizados.
"""
import logging

from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.urls import reverse
from django.views import View

from .crypto import TokenCryptoError
from .conf import _keys_are_valid
from .images import ImageValidationError, sanitize_image
from .models import AiProviderKey, GeneratedImage
from .services import deepseek, gemini

logger = logging.getLogger("apps.social.meta")

EXAMPLE_TEXT_PROMPT = (
    "Escreva um post curto e animado anunciando a promoção de fim de semana da minha padaria: pão francês com 20% de "
    "desconto no sábado e no domingo, das 7h às 11h. Tom amigável, com 2 emojis e um convite para visitar a loja."
)
MSG_PROMPT = "Escreva o prompt da imagem."
MSG_PROMPT_LONG = f"O prompt pode ter no máximo {settings.GEMINI_PROMPT_MAX_LENGTH} caracteres."
MSG_KEY_EMPTY = "Informe a chave de API."
MSG_KEY_SAVED = "Chave cadastrada."
MSG_NO_CRYPTO = "Chave de criptografia do servidor indisponível: não é possível guardar a chave."
MSG_UNREADABLE = "A chave cadastrada não pôde ser lida. Cadastre-a novamente."


def _json(data, status=200):
    response = JsonResponse(data, status=status)
    response["Cache-Control"] = "no-store"
    return response


def _error(message, status=400, code="invalid"):
    return _json({"ok": False, "error": message, "code": code}, status=status)


PROVIDERS = (AiProviderKey.GEMINI, AiProviderKey.DEEPSEEK)
SERVER_KEYS = {AiProviderKey.GEMINI: "GEMINI_API_KEY", AiProviderKey.DEEPSEEK: "DEEPSEEK_API_KEY"}


def request_provider(request) -> str:
    """Provedor pedido (padrão: gemini). Só valores conhecidos."""
    value = request.POST.get("provider", AiProviderKey.GEMINI)
    return value if value in PROVIDERS else AiProviderKey.GEMINI


def key_status(user, provider=AiProviderKey.GEMINI) -> dict:
    """Estado da chave para a tela: nunca a chave, só se há e os 4 últimos caracteres."""
    own = AiProviderKey.objects.filter(owner=user, provider=provider).first()
    server = bool(getattr(settings, SERVER_KEYS[provider], ""))
    return {
        "provider": provider,
        "has_key": bool(own) or server,
        "own": bool(own),
        "last4": own.last4 if own else "",
        "server": server and not own,
    }


def resolve_key(user, provider=AiProviderKey.GEMINI) -> str:
    own = AiProviderKey.objects.filter(owner=user, provider=provider).first()
    if own:
        return own.get_key()
    return getattr(settings, SERVER_KEYS[provider], "") or ""


class GenerateImageView(View):
    http_method_names = ["post", "options"]

    def post(self, request):
        prompt = request.POST.get("prompt", "").strip()
        model = request.POST.get("model", "")
        if not prompt:
            return _error(MSG_PROMPT)
        if len(prompt) > settings.GEMINI_PROMPT_MAX_LENGTH:
            return _error(MSG_PROMPT_LONG)
        if model not in gemini.allowed_models():
            return _error(gemini.MESSAGES["invalid_model"])
        try:
            api_key = resolve_key(request.user)
        except TokenCryptoError:
            return _error(MSG_UNREADABLE, code="unreadable")
        if not api_key:
            return _error(gemini.MESSAGES["no_key"], code="no_key")
        try:
            data, _ = gemini.generate_image(api_key, model, prompt)
        except gemini.GeminiError as exc:
            status = 504 if exc.code == "timeout" else 502
            return _error(str(exc), status=status, code=exc.code)
        try:  # mesma sanitização/limites de uma imagem enviada (ADR-0005)
            from django.core.files.uploadedfile import SimpleUploadedFile

            sanitized = sanitize_image(SimpleUploadedFile("gerada", data))
        except ImageValidationError as exc:
            return _error(str(exc), status=502, code="bad_image")

        GeneratedImage.purge_expired()
        # Regenerar substitui a imagem gerada anterior do usuário.
        for old in GeneratedImage.objects.filter(owner=request.user):
            old.file.delete(save=False)
            old.delete()
        item = GeneratedImage(owner=request.user, content_type=sanitized.content_type)
        item.file.save(sanitized.content.name, sanitized.content, save=True)
        return _json({"ok": True, "id": item.pk, "url": reverse("social:ai_image", args=[item.pk])})


class GeneratedImageView(View):
    """Entrega a imagem gerada só ao dono (sem URL pública)."""

    def get(self, request, pk):
        item = GeneratedImage.objects.filter(pk=pk, owner=request.user).first()
        if not item or item.is_expired():
            raise Http404("Imagem indisponível.")
        try:
            handle = item.file.open("rb")
        except FileNotFoundError:
            raise Http404("Imagem indisponível.") from None
        response = FileResponse(handle, content_type=item.content_type)
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        response["Content-Disposition"] = "inline"
        return response


class SaveKeyView(View):
    http_method_names = ["post", "options"]

    def post(self, request):
        provider = request_provider(request)
        key = request.POST.get("api_key", "").strip()
        if not key:
            return _error(MSG_KEY_EMPTY)
        if not _keys_are_valid():
            return _error(MSG_NO_CRYPTO, status=500, code="no_crypto")
        record = AiProviderKey.objects.filter(owner=request.user, provider=provider).first() or AiProviderKey(
            owner=request.user, provider=provider
        )
        record.set_key(key)
        record.save()
        return _json({"ok": True, "message": MSG_KEY_SAVED, "key": key_status(request.user, provider)})


class RemoveKeyView(View):
    http_method_names = ["post", "options"]

    def post(self, request):
        provider = request_provider(request)
        AiProviderKey.objects.filter(owner=request.user, provider=provider).delete()
        return _json({"ok": True, "message": "Chave removida.", "key": key_status(request.user, provider)})


class TestKeyView(View):
    """Testa a chave: a digitada no campo (sem salvar) ou, vazio, a cadastrada/do servidor. Nada é gerado nem guardado."""

    http_method_names = ["post", "options"]

    def post(self, request):
        provider = request_provider(request)
        typed = request.POST.get("api_key", "").strip()
        try:
            api_key = typed or resolve_key(request.user, provider)
        except TokenCryptoError:
            return _error(MSG_UNREADABLE, code="unreadable")
        checker = deepseek.check_key if provider == AiProviderKey.DEEPSEEK else gemini.check_key
        try:
            checker(api_key)
        except gemini.GeminiError as exc:
            return _error(str(exc), status=504 if exc.code == "timeout" else 502, code=exc.code)
        return _json({"ok": True, "message": "Chave válida."})


class GenerateTextView(View):
    """Gera o texto da publicação com o provedor escolhido (Gemini ou DeepSeek). Nada é salvo nem publicado (spec 0008, AC-9)."""

    http_method_names = ["post", "options"]

    def post(self, request):
        prompt = request.POST.get("prompt", "").strip()
        provider = request_provider(request)
        model = settings.DEEPSEEK_TEXT_MODEL if provider == AiProviderKey.DEEPSEEK else settings.GEMINI_TEXT_MODEL
        if not model:
            return _error("A geração de texto com este provedor está desativada.", code="disabled")
        if not prompt:
            return _error(MSG_PROMPT)
        if len(prompt) > settings.GEMINI_PROMPT_MAX_LENGTH:
            return _error(MSG_PROMPT_LONG)
        label = "DeepSeek" if provider == AiProviderKey.DEEPSEEK else "Gemini"
        try:
            api_key = resolve_key(request.user, provider)
        except TokenCryptoError:
            return _error(MSG_UNREADABLE, code="unreadable")
        if not api_key:
            return _error(gemini.GeminiError("no_key", label=label).args[0], code="no_key")
        generator = deepseek.generate_text if provider == AiProviderKey.DEEPSEEK else gemini.generate_text
        try:
            text = generator(api_key, model, prompt)
        except gemini.GeminiError as exc:
            return _error(str(exc), status=504 if exc.code == "timeout" else 502, code=exc.code)
        return _json({"ok": True, "text": text[: settings.PUBLICATION_MAX_TEXT_LENGTH]})
