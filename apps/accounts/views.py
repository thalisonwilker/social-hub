from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.contrib.messages.views import SuccessMessageMixin
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render, resolve_url
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView

from . import idempotency
from .forms import MSG_EMAIL_TAKEN, LoginForm, SignupForm, StyledPasswordChangeForm
from .models import SignupIdempotencyKey

SIGNUP_SUCCESS_MESSAGE = "Sua conta foi criada. Entre com seu e-mail e senha."
SIGNUP_EXPIRED_MESSAGE = "O formulário expirou. Revise os dados e envie novamente."


@method_decorator(login_not_required, name="dispatch")
class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


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
