from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.db.models import Q

from .validators import (
    PasswordCompositionValidator,
    normalize_email,
    validate_person_name,
)

INPUT_CLASS = "input"

MSG_EMAIL_INVALID = "Informe um e-mail válido."
MSG_EMAIL_TAKEN = "Este e-mail já está cadastrado."
MSG_PASSWORD_REQUIRED = "Informe uma senha."
MSG_LOGIN_PASSWORD_REQUIRED = "Informe sua senha."
MSG_PASSWORD_MISMATCH = "As senhas não coincidem."
MSG_TERMS_REQUIRED = "Você precisa aceitar os Termos de Uso e a Política de Privacidade."


class LoginForm(forms.Form):
    """Campos do login (spec 0014): só valida e normaliza; a autenticação fica na view."""

    email = forms.EmailField(
        label="E-mail",
        max_length=254,
        error_messages={
            "required": MSG_EMAIL_INVALID,
            "invalid": MSG_EMAIL_INVALID,
            "max_length": MSG_EMAIL_INVALID,
        },
    )
    password = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput,
        error_messages={"required": MSG_LOGIN_PASSWORD_REQUIRED},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update(
            {
                "class": INPUT_CLASS,
                "autofocus": True,
                "autocomplete": "username",
                "inputmode": "email",
                "aria-describedby": "email-error",
            }
        )
        self.fields["password"].widget.attrs.update(
            {"class": INPUT_CLASS, "autocomplete": "current-password", "aria-describedby": "password-error"}
        )

    def clean_email(self):
        return normalize_email(self.cleaned_data.get("email"))


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = INPUT_CLASS
            field.widget.attrs["autocomplete"] = (
                "current-password" if name == "old_password" else "new-password"
            )


def email_taken(email: str) -> bool:
    """Há usuário com este e-mail — no `email` ou no `username` —, sem diferenciar maiúsculas."""
    return get_user_model().objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists()


def _signup_password_validators():
    """Validadores padrão do projeto, trocando o de tamanho mínimo pela regra de composição."""
    validators = [
        v
        for v in password_validation.get_default_password_validators()
        if not isinstance(v, password_validation.MinimumLengthValidator)
    ]
    return [PasswordCompositionValidator(), *validators]


class SignupForm(forms.Form):
    """Cadastro de novo usuário (spec 0013). O servidor revalida tudo o que o navegador validou."""

    first_name = forms.CharField(label="Nome", required=False, strip=False)
    last_name = forms.CharField(label="Sobrenome", required=False, strip=False)
    email = forms.EmailField(
        label="E-mail",
        max_length=254,
        error_messages={
            "required": MSG_EMAIL_INVALID,
            "invalid": MSG_EMAIL_INVALID,
            "max_length": MSG_EMAIL_INVALID,
        },
    )
    password1 = forms.CharField(
        label="Senha",
        strip=False,
        widget=forms.PasswordInput,
        error_messages={"required": MSG_PASSWORD_REQUIRED},
    )
    password2 = forms.CharField(
        label="Confirmar senha",
        strip=False,
        widget=forms.PasswordInput,
        error_messages={"required": MSG_PASSWORD_MISMATCH},
    )
    accept_terms = forms.BooleanField(
        label="Li e aceito os Termos de Uso e a Política de Privacidade",
        error_messages={"required": MSG_TERMS_REQUIRED},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        autocomplete = {
            "first_name": "given-name",
            "last_name": "family-name",
            "email": "email",
            "password1": "new-password",
            "password2": "new-password",
        }
        for name, value in autocomplete.items():
            self.fields[name].widget.attrs.update(
                {"class": INPUT_CLASS, "autocomplete": value, "aria-describedby": f"{name}-error"}
            )
        self.fields["first_name"].widget.attrs["maxlength"] = 150
        self.fields["last_name"].widget.attrs["maxlength"] = 150
        self.fields["email"].widget.attrs["inputmode"] = "email"
        self.fields["accept_terms"].widget.attrs["aria-describedby"] = "accept_terms-error"

    def full_clean(self):
        super().full_clean()
        # Campo com erro do servidor fica marcado como inválido também sem JavaScript (spec 0015, AC-2).
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs["aria-invalid"] = "true"

    def clean_first_name(self):
        return validate_person_name(self.cleaned_data.get("first_name"), "Informe seu nome.")

    def clean_last_name(self):
        return validate_person_name(self.cleaned_data.get("last_name"), "Informe seu sobrenome.")

    def clean_email(self):
        email = normalize_email(self.cleaned_data.get("email"))
        if email_taken(email):
            raise ValidationError(MSG_EMAIL_TAKEN, code="email_taken")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 != password1:
            raise ValidationError(MSG_PASSWORD_MISMATCH, code="password_mismatch")
        return password2

    def _post_clean(self):
        super()._post_clean()
        password = self.cleaned_data.get("password1")
        if not password:
            return
        # Usuário provisório só para o validador de similaridade (nome/e-mail).
        probe = get_user_model()(
            username=self.cleaned_data.get("email", ""),
            email=self.cleaned_data.get("email", ""),
            first_name=self.cleaned_data.get("first_name", ""),
            last_name=self.cleaned_data.get("last_name", ""),
        )
        try:
            password_validation.validate_password(password, probe, _signup_password_validators())
        except ValidationError as error:
            self.add_error("password1", error)

    def save(self):
        """Cria o usuário: `username` = `email` normalizado, senha com hash, ativo e não staff."""
        data = self.cleaned_data
        return get_user_model().objects.create_user(
            username=data["email"],
            email=data["email"],
            password=data["password1"],
            first_name=data["first_name"],
            last_name=data["last_name"],
        )


class PasswordResetRequestForm(forms.Form):
    """Pedido de recuperação (spec 0016): só o e-mail, validado e normalizado."""

    email = forms.EmailField(
        label="E-mail",
        max_length=254,
        error_messages={"required": MSG_EMAIL_INVALID, "invalid": MSG_EMAIL_INVALID, "max_length": MSG_EMAIL_INVALID},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update(
            {"class": INPUT_CLASS, "autofocus": True, "autocomplete": "email", "inputmode": "email",
             "aria-describedby": "email-error"}
        )

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs["aria-invalid"] = "true"

    def clean_email(self):
        return normalize_email(self.cleaned_data.get("email"))


class SetNewPasswordForm(forms.Form):
    """Nova senha (spec 0016): mesma política e mensagens do cadastro (spec 0013)."""

    password1 = forms.CharField(
        label="Nova senha", strip=False, widget=forms.PasswordInput,
        error_messages={"required": MSG_PASSWORD_REQUIRED},
    )
    password2 = forms.CharField(
        label="Confirmar senha", strip=False, widget=forms.PasswordInput,
        error_messages={"required": MSG_PASSWORD_MISMATCH},
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        for name in ("password1", "password2"):
            self.fields[name].widget.attrs.update(
                {"class": INPUT_CLASS, "autocomplete": "new-password", "aria-describedby": f"{name}-error"}
            )
        self.fields["password1"].widget.attrs["autofocus"] = True

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs["aria-invalid"] = "true"

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 != password1:
            raise ValidationError(MSG_PASSWORD_MISMATCH, code="password_mismatch")
        return password2

    def _post_clean(self):
        super()._post_clean()
        password = self.cleaned_data.get("password1")
        if password:
            try:
                password_validation.validate_password(password, self.user, _signup_password_validators())
            except ValidationError as error:
                self.add_error("password1", error)
