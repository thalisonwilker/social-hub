import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.contrib.messages.views import SuccessMessageMixin
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render, resolve_url
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views import View
from django.views.generic import TemplateView

from . import idempotency, login_throttle
from .forms import MSG_EMAIL_TAKEN, LoginForm, SignupForm, StyledPasswordChangeForm
from .models import LoginAttempt, SignupIdempotencyKey

SIGNUP_SUCCESS_MESSAGE = "Sua conta foi criada com sucesso! Faça login para continuar."
SIGNUP_EXPIRED_MESSAGE = "O formulário expirou. Revise os dados e envie novamente."


LOGIN_INVALID_MESSAGE = "E-mail ou senha inválidos"
LOGIN_BAD_KEY_MESSAGE = "Não foi possível processar o login. Recarregue a página e tente novamente."
LOGIN_DUPLICATE_MESSAGE = "Esta tentativa de login já foi processada. Recarregue a página."
LOGIN_THROTTLED_MESSAGE = "Muitas tentativas. Tente novamente em alguns minutos."

login_logger = logging.getLogger("apps.accounts.login")


@method_decorator(
    [login_not_required, sensitive_post_parameters("password"), csrf_protect, never_cache], name="dispatch"
)
class LoginView(View):
    """Jornada de login (spec 0014). Ordem do POST conforme a matriz de decisão da spec:
    campos → chave → repetição → bloqueio → autenticação → tentativa gravada → `login()`.
    """

    template_name = "accounts/login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:  # inclui a repetição de um login que já criou a sessão
            return redirect(self._success_url(request))
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return self._render(request, LoginForm())

    def post(self, request):
        login_throttle.purge_old()
        ip = login_throttle.client_ip(request)
        form = LoginForm(request.POST)
        if not form.is_valid():  # AC-3
            self._log("campos_invalidos", ip)
            return self._render(request, form, status=400)

        key = login_throttle.parse_key(request.POST.get("chave_idempotencia"))
        if key is None:  # AC-7
            self._log("chave_invalida", ip)
            return self._render(request, form, error=LOGIN_BAD_KEY_MESSAGE, status=400)

        email_hash = login_throttle.hash_email(form.cleaned_data["email"])
        previous = LoginAttempt.objects.filter(key=key).first()
        if previous is not None:  # AC-6
            return self._repeat(request, form, previous, email_hash, ip)

        wait = login_throttle.retry_after(email_hash, ip)
        if wait is not None:  # AC-5
            self._log("bloqueado", ip, email_hash)
            response = self._render(request, form, error=LOGIN_THROTTLED_MESSAGE, status=429)
            response["Retry-After"] = str(wait)
            return response

        user = authenticate(request, username=form.cleaned_data["email"], password=form.cleaned_data["password"])
        try:
            with transaction.atomic():
                LoginAttempt.objects.create(key=key, email_hash=email_hash, ip=ip, succeeded=user is not None)
        except IntegrityError:  # corrida: outra requisição com a mesma chave gravou antes (AC-6)
            return self._repeat(request, form, LoginAttempt.objects.get(key=key), email_hash, ip)

        if user is None:  # AC-2
            self._log("falha", ip, email_hash)
            return self._render(request, form, error=LOGIN_INVALID_MESSAGE, status=401)

        auth_login(request, user)  # troca a chave da sessão (proteção contra fixação)
        self._log("sucesso", ip, email_hash)
        return redirect(self._success_url(request))

    def _repeat(self, request, form, previous, email_hash, ip):
        """Repetição de uma tentativa já gravada: nunca autentica, nunca cria sessão nem conta falha."""
        if previous.email_hash != email_hash or previous.succeeded:
            # Outro e-mail com a mesma chave, ou sucesso cuja sessão este navegador ainda não tem.
            self._log("repeticao_conflito", ip, email_hash)
            return self._render(request, form, error=LOGIN_DUPLICATE_MESSAGE, status=409)
        self._log("repeticao_falha", ip, email_hash)
        return self._render(request, form, error=LOGIN_INVALID_MESSAGE, status=401)

    def _success_url(self, request):
        url = request.POST.get("next") or request.GET.get("next")
        if url and url_has_allowed_host_and_scheme(
            url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return url
        return resolve_url(settings.LOGIN_REDIRECT_URL)

    def _render(self, request, form, error=None, status=200):
        next_url = request.POST.get("next") or request.GET.get("next") or ""
        context = {
            "form": form,
            "error": error,
            "next": next_url,
            # Reserva para quem está sem JavaScript; com JS, a página gera a própria chave (AC-7).
            "chave_idempotencia": str(uuid.uuid4()),
        }
        return render(request, self.template_name, context, status=status)

    @staticmethod
    def _log(event, ip, email_hash=None):
        """Só evento, IP e prefixo do hash do e-mail — nunca senha, e-mail, chave ou sessão (AC-10)."""
        login_logger.info("login %s ip=%s email=%s", event, ip, email_hash[:12] if email_hash else "-")


class LogoutView(auth_views.LogoutView):
    """Encerra a sessão (somente via POST)."""


class ProfileView(TemplateView):
    template_name = "accounts/profile.html"


class PasswordChangeView(SuccessMessageMixin, auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("accounts:profile")
    success_message = "Senha alterada com sucesso."


@method_decorator(login_not_required, name="dispatch")
class LegalPageView(TemplateView):
    """Termos de Uso e Política de Privacidade — páginas públicas provisórias (spec 0013, AC-10)."""


@method_decorator(login_not_required, name="dispatch")
class SignupView(View):
    """Cadastro de novo usuário (spec 0013).

    Ordem no POST: chave de idempotência (AC-12) → repetição de envio já concluído (AC-11) →
    validação dos dados (AC-5/6) → chave + usuário na mesma transação (AC-7/11).
    """

    template_name = "accounts/signup.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:  # AC-2
            return redirect(resolve_url(settings.LOGIN_REDIRECT_URL))
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return self._render(request, SignupForm())

    def post(self, request):
        key = idempotency.read_key(request.POST.get("chave_idempotencia"))
        if key is None:  # AC-12: sem chave, assinatura inválida ou expirada
            return self._render(request, self._form_from_post(request), notice=SIGNUP_EXPIRED_MESSAGE)

        if SignupIdempotencyKey.objects.filter(key=key).exists():  # AC-11: repetição após sucesso
            return self._success(request)

        form = SignupForm(request.POST)
        if not form.is_valid():
            return self._render(request, form)

        try:
            with transaction.atomic():
                user = form.save()
                SignupIdempotencyKey.objects.create(key=key, user=user)
        except IntegrityError:
            # Corrida: outra requisição com a mesma chave venceu (AC-11) ou o e-mail foi usado
            # por outro envio entre a validação e a gravação (username único).
            if SignupIdempotencyKey.objects.filter(key=key).exists():
                return self._success(request)
            form.add_error("email", MSG_EMAIL_TAKEN)
            return self._render(request, form)
        return self._success(request)

    def _success(self, request):
        messages.success(request, SIGNUP_SUCCESS_MESSAGE)
        return redirect("accounts:login")

    def _form_from_post(self, request):
        """Formulário sem validação, só com os dados digitados (sem senhas)."""
        post = request.POST
        return SignupForm(
            initial={
                "first_name": post.get("first_name", ""),
                "last_name": post.get("last_name", ""),
                "email": post.get("email", ""),
                "accept_terms": bool(post.get("accept_terms")),
            }
        )

    def _render(self, request, form, notice=None):
        context = {"form": form, "chave_idempotencia": idempotency.issue_key(), "notice": notice}
        return render(request, self.template_name, context)
