from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.forms import SignupForm

from .helpers import STRONG_PASSWORD, signup_data

User = get_user_model()


class SignupFormTests(TestCase):
    def form(self, **overrides):
        return SignupForm(signup_data(**overrides))

    def test_valid_form_normalizes_and_saves(self):
        form = self.form(first_name="  Maria ", last_name=" da Silva ", email=" Maria@Exemplo.COM ")
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual((user.username, user.email), ("maria@exemplo.com", "maria@exemplo.com"))
        self.assertEqual((user.first_name, user.last_name), ("Maria", "da Silva"))
        self.assertTrue(user.check_password(STRONG_PASSWORD))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_all_errors_in_portuguese(self):
        form = SignupForm({"first_name": "", "last_name": "1", "email": "x", "password1": "abc", "password2": "abd"})
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["first_name"], ["Informe seu nome."])
        self.assertEqual(form.errors["last_name"], ["Use apenas letras, espaços, hífen ou apóstrofo."])
        self.assertEqual(form.errors["email"], ["Informe um e-mail válido."])
        self.assertIn("A senha precisa de pelo menos uma letra maiúscula.", form.errors["password1"])
        self.assertEqual(form.errors["password2"], ["As senhas não coincidem."])
        self.assertEqual(
            form.errors["accept_terms"], ["Você precisa aceitar os Termos de Uso e a Política de Privacidade."]
        )

    def test_email_taken_ignores_case_in_email_and_username(self):
        User.objects.create_user("email@email.com", email="email@email.com", password="x")
        User.objects.create_user("ana@x.com", password="x")  # usuário antigo sem e-mail
        for email in ("eMaiL@EMAil.com", "ANA@x.com"):
            form = self.form(email=email)
            self.assertFalse(form.is_valid())
            self.assertEqual(form.errors["email"], ["Este e-mail já está cadastrado."], email)

    def test_email_too_long(self):
        form = self.form(email=("a" * 250) + "@x.com")
        self.assertEqual(form.errors["email"], ["Informe um e-mail válido."])

    def test_django_validators_still_apply(self):
        form = self.form(password1="Maria@Exemplo.com1", password2="Maria@Exemplo.com1")
        self.assertFalse(form.is_valid())  # parecida com o e-mail (UserAttributeSimilarityValidator)
        self.assertIn("password1", form.errors)

    def test_password_not_stripped(self):
        form = self.form(password1=" Quarto#Azul42", password2="Quarto#Azul42")
        self.assertEqual(form.errors["password2"], ["As senhas não coincidem."])
