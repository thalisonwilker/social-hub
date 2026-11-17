import logging

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View

from apps.core.views import PlaceholderView  # noqa: F401  (usado em urls.py)

from .conf import meta_configured
from .crypto import TokenCryptoError
from .services import facebook_connect
from .services.meta import GraphClient, MetaApiError

logger = logging.getLogger("apps.social.meta")

MSG_NOT_CONFIGURED = "Integração com a Meta não configurada."
MSG_CANCELLED = "Autorização cancelada."
MSG_STATE = "Não foi possível validar a conexão. Tente novamente."
MSG_META_FAILURE = "Não foi possível concluir a conexão com a Meta. Tente novamente."
MSG_NO_PAGES = (
    "Nenhuma Página encontrada nesta conta. Verifique se você administra uma Página "
    "e se a concedeu no login."
)
MSG_NO_PERMISSION = "Encontramos Páginas, mas você não tem permissão para gerenciá-las."
MSG_EXPIRED = "A seleção expirou. Conecte novamente."


class FacebookConnectView(View):
    """Inicia o OAuth (somente POST, protegido por CSRF)."""

    http_method_names = ["post", "options"]

    def post(self, request):
        if not meta_configured():
            messages.error(request, MSG_NOT_CONFIGURED)
            return redirect("social:accounts")
        state = facebook_connect.new_state(request.session)
        logger.info("oauth_started")
        return redirect(GraphClient.from_settings().login_url(state))


class FacebookCallbackView(View):
    """Recebe o retorno da Meta (code + state)."""

    http_method_names = ["get", "options"]

    def get(self, request):
        if not meta_configured():
            messages.error(request, MSG_NOT_CONFIGURED)
            return redirect("social:accounts")

        if request.GET.get("error"):
            request.session.pop(facebook_connect.STATE_KEY, None)
            messages.info(request, MSG_CANCELLED)
            return redirect("social:accounts")

        if not facebook_connect.consume_state(request.session, request.GET.get("state", "")):
            logger.warning("oauth_state_rejected")
            messages.error(request, MSG_STATE)
            return redirect("social:accounts")

        code = request.GET.get("code", "")
        if not code:
            messages.error(request, MSG_META_FAILURE)
            return redirect("social:accounts")

        try:
            result = facebook_connect.fetch_pages(request.session, code)
        except (MetaApiError, TokenCryptoError):
            messages.error(request, MSG_META_FAILURE)
            return redirect("social:accounts")

        if result.usable == 0:
            messages.warning(request, MSG_NO_PERMISSION if result.skipped else MSG_NO_PAGES)
            return redirect("social:accounts")
        return redirect("social:facebook_select")


class FacebookSelectView(View):
    """Escolha de uma ou mais Páginas antes de conectá-las."""

    template_name = "social/facebook_select.html"

    def _render(self, request, pages, *, error=None, status=200):
        from .models import SocialAccount

        connected = set(
            SocialAccount.objects.filter(
                owner=request.user, platform=SocialAccount.Platform.FACEBOOK_PAGE
            ).values_list("external_id", flat=True)
        )
        items = [{**p, "connected": p["id"] in connected} for p in pages]
        return render(
            request,
            self.template_name,
            {"page_title": "Selecionar Páginas", "pages": items, "error": error},
            status=status,
        )

    def get(self, request):
        pages = facebook_connect.pending_pages(request.session)
        if pages is None:
            messages.error(request, MSG_EXPIRED)
            return redirect("social:accounts")
        return self._render(request, pages)

    def post(self, request):
        try:
            accounts = facebook_connect.save_selected(
                request.user, request.session, request.POST.getlist("pages")
            )
        except facebook_connect.SelectionError as exc:
            if exc.reason == "expired":
                messages.error(request, MSG_EXPIRED)
                return redirect("social:accounts")
            pages = facebook_connect.pending_pages(request.session) or []
            if exc.reason == "empty":
                return self._render(request, pages, error="Marque ao menos uma Página.")
            return self._render(
                request, pages, error="Seleção inválida. Tente novamente.", status=400
            )
        count = len(accounts)
        messages.success(request, f"{count} Página conectada." if count == 1 else f"{count} Páginas conectadas.")
        return redirect("social:accounts")
