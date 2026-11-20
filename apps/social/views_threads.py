"""Conexão do Threads: iniciar o OAuth e receber o callback. Ver specs/0004-threads-conectar-e-publicar."""
import logging

from django.contrib import messages
from django.shortcuts import redirect
from django.views import View

from .conf import threads_configured, threads_redirect_host
from .crypto import TokenCryptoError
from .services import facebook_connect, profiles, threads_connect
from .services.meta import MetaApiError
from .services.threads import ThreadsClient

logger = logging.getLogger("apps.social.meta")

MSG_NOT_CONFIGURED = "Integração com o Threads não configurada."
MSG_CANCELLED = "Autorização cancelada."
MSG_STATE = "Não foi possível validar a conexão. Tente novamente."
MSG_FAILURE = "Não foi possível concluir a conexão com o Threads. Tente novamente."


class ThreadsConnectView(View):
    """Inicia o OAuth (somente POST, protegido por CSRF). Deve ser feito pelo host do redirect."""

    http_method_names = ["post", "options"]

    def post(self, request):
        if not threads_configured():
            messages.error(request, MSG_NOT_CONFIGURED)
            return redirect(profiles.after(request))

        expected = threads_redirect_host()
        if request.get_host() != expected:
            messages.error(request, f"Acesse o Social Hub por {expected} para conectar o Threads.")
            return redirect(profiles.after(request))

        state = facebook_connect.new_state(request.session, threads_connect.STATE_KEY)
        logger.info("threads_oauth_started")
        return redirect(ThreadsClient.from_settings().login_url(state))


class ThreadsCallbackView(View):
    """Recebe o retorno do Threads (code + state)."""

    http_method_names = ["get", "options"]

    def get(self, request):
        if not threads_configured():
            messages.error(request, MSG_NOT_CONFIGURED)
            return redirect(profiles.after(request))

        if request.GET.get("error"):
            request.session.pop(threads_connect.STATE_KEY, None)
            messages.info(request, MSG_CANCELLED)
            return redirect(profiles.after(request))

        if not facebook_connect.consume_state(request.session, request.GET.get("state", ""), threads_connect.STATE_KEY):
            logger.warning("threads_state_rejected")
            messages.error(request, MSG_STATE)
            return redirect(profiles.after(request))

        code = request.GET.get("code", "")
        if not code:
            messages.error(request, MSG_FAILURE)
            return redirect(profiles.after(request))

        try:
            account = threads_connect.connect_profile(request.user, code)
        except (MetaApiError, TokenCryptoError) as exc:
            logger.warning("oauth_failed platform=threads reason=%s", type(exc).__name__)
            messages.error(request, MSG_FAILURE)
            return redirect(profiles.after(request))

        messages.success(request, f"Perfil @{account.username or account.name} conectado.")
        profiles.adopt(request, [account])
        return redirect(profiles.after(request, ok=True))
