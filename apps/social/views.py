import logging

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.core.views import PlaceholderView  # noqa: F401  (usado em urls.py)

from .conf import evolution_configured, meta_configured, threads_configured
from .crypto import TokenCryptoError
from .services import facebook_connect
from .models import SocialAccount
from .services import evolution_connect, threads_tokens
from .services.evolution import EvolutionApiError, EvolutionClient
from .services.threads import ThreadsClient
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
        except (MetaApiError, TokenCryptoError) as exc:
            logger.warning("oauth_failed reason=%s", type(exc).__name__)
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


class AccountsView(TemplateView):
    """Lista as contas sociais do usuário logado (nunca expõe tokens)."""

    template_name = "social/accounts.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        threads_tokens.expire_stale_tokens(self.request.user)  # validade local, sem rede
        context.update(
            page_title="Contas conectadas",
            configured=meta_configured(),
            threads_configured=threads_configured(),
            evolution_configured=evolution_configured(),
            accounts=SocialAccount.objects.filter(owner=self.request.user),
        )
        return context


class AccountActionView(View):
    """Base das ações POST sobre uma conta; só o dono acessa (404 caso contrário)."""

    http_method_names = ["post", "options"]

    def get_account(self, request, pk):
        return get_object_or_404(SocialAccount, pk=pk, owner=request.user)


class AccountCheckView(AccountActionView):
    """Testa a conta (Facebook: `GET /{page_id}`; Threads: renova se devido e lê o perfil) e atualiza o status."""

    MSG_CANNOT_CHECK = "Não foi possível verificar agora. Tente novamente em instantes."

    def post(self, request, pk):
        account = self.get_account(request, pk)
        if account.platform == SocialAccount.Platform.THREADS:
            return self._check_threads(request, account)
        if account.platform == SocialAccount.Platform.WHATSAPP_STATUS:
            return self._check_whatsapp(request, account)
        return self._check_facebook(request, account)

    def _save(self, account, **fields):
        for name, value in fields.items():
            setattr(account, name, value)
        account.last_checked_at = timezone.now()
        account.save(update_fields=[*fields, "last_checked_at", "updated_at"])

    def _needs_reauth(self, request, account, code):
        self._save(account, status=SocialAccount.Status.NEEDS_REAUTH, last_error=f"Meta erro {code}")
        messages.warning(request, f"Reconexão necessária para “{account.name}”.")

    def _ok(self, request, account):
        self._save(account, status=SocialAccount.Status.ACTIVE, last_error="")
        messages.success(request, f"“{account.name}” está conectada e funcionando.")

    def _check_facebook(self, request, account):
        if not meta_configured():
            messages.error(request, MSG_NOT_CONFIGURED)
            return redirect("social:accounts")
        try:
            GraphClient.from_settings().get_page(account.external_id, account.get_token())
        except MetaApiError as exc:
            if exc.is_token_error:
                self._needs_reauth(request, account, exc.code)
            else:
                messages.error(request, self.MSG_CANNOT_CHECK)
            return redirect("social:accounts")
        except TokenCryptoError:
            messages.error(request, self.MSG_CANNOT_CHECK)
            return redirect("social:accounts")
        self._ok(request, account)
        return redirect("social:accounts")

    def _check_whatsapp(self, request, account):
        """Consulta o estado da conexão da instância: `open` → ativa; desconectada/chave recusada → Reconexão necessária."""
        if not evolution_configured():
            messages.error(request, evolution_connect.MSG_NOT_CONFIGURED)
            return redirect("social:accounts")
        try:
            state = EvolutionClient.from_settings().connection_state(account.external_id, account.get_token())
        except EvolutionApiError as exc:
            if exc.code in evolution_connect.REAUTH_CODES:
                evolution_connect.needs_reauth(account)
                messages.warning(request, f"Reconexão necessária para “{account.name}”.")
            else:
                messages.error(request, self.MSG_CANNOT_CHECK)
            return redirect("social:accounts")
        except TokenCryptoError:
            messages.error(request, self.MSG_CANNOT_CHECK)
            return redirect("social:accounts")
        if state != evolution_connect.OPEN:
            evolution_connect.needs_reauth(account)
            messages.warning(request, f"Reconexão necessária para “{account.name}”.")
            return redirect("social:accounts")
        self._ok(request, account)
        return redirect("social:accounts")

    def _check_threads(self, request, account):
        if not threads_configured():
            messages.error(request, "Integração com o Threads não configurada.")
            return redirect("social:accounts")
        client = ThreadsClient.from_settings()
        try:
            if not threads_tokens.ensure_fresh(account, client=client):  # expirado ou token recusado na renovação
                messages.warning(request, f"Reconexão necessária para “{account.name}”.")
                return redirect("social:accounts")
            client.get_profile(account.external_id, account.get_token())
        except MetaApiError as exc:
            if exc.is_token_error:
                self._needs_reauth(request, account, exc.code)
            else:
                messages.error(request, self.MSG_CANNOT_CHECK)
            return redirect("social:accounts")
        except TokenCryptoError:
            messages.error(request, self.MSG_CANNOT_CHECK)
            return redirect("social:accounts")
        self._ok(request, account)
        return redirect("social:accounts")


class AccountDisconnectView(AccountActionView):
    """Apaga a conta e o token localmente."""

    def post(self, request, pk):
        account = self.get_account(request, pk)
        name = account.name
        account.delete()
        logger.info("account_disconnected")
        messages.success(request, f"“{name}” foi desconectada.")
        return redirect("social:accounts")
