from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from .helpers import SIGNUP_URL, signup_data

User = get_user_model()
LOGIN_URL = reverse("accounts:login")
SUCCESS = "Sua conta foi criada com sucesso! Faça login para continuar."  # spec 0015, AC-6


class SignupViewTests(TestCase):
    def test_AC_1_public_signup_page(self):
        response = self.client.get(SIGNUP_URL)
        self.assertEqual(response.status_code, 200)
        for text in ('name="first_name"', 'name="last_name"', 'name="email"', 'name="password1"',
                     'name="password2"', 'name="accept_terms"', 'name="chave_idempotencia"',
                     "data-password-toggle", 'id="signup-submit"', "Criar conta", "Continuar com Google",
                     reverse("accounts:terms"), reverse("accounts:privacy"), "Já tem conta?", "js/signup.js"):
            self.assertContains(response, text, msg_prefix=text)
        # Sem JS o botão nasce habilitado (o JS é quem desabilita).
        self.assertNotContains(response, 'id="signup-submit" disabled')

    def test_AC_1_login_links_to_signup(self):
        self.assertContains(self.client.get(LOGIN_URL), f'href="{SIGNUP_URL}"')

    def test_AC_2_authenticated_user_is_redirected(self):
        self.client.force_login(User.objects.create_user("u", password="x"))
        self.assertRedirects(self.client.get(SIGNUP_URL), reverse("social:profile_select"), fetch_redirect_response=False)
        self.assertRedirects(self.client.post(SIGNUP_URL, signup_data()), reverse("social:profile_select"), fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), 1)

    def test_AC_5_server_revalidates_everything(self):
        data = signup_data(first_name="", last_name="<b>x</b>", email="nao-e-email",
                           password1="fraca", password2="outra", accept_terms=None)
        response = self.client.post(SIGNUP_URL, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)
        for message in ("Informe seu nome.", "Use apenas letras, espaços, hífen ou apóstrofo.",
                        "Informe um e-mail válido.", "A senha precisa de pelo menos uma letra maiúscula.",
                        "As senhas não coincidem.",
                        "Você precisa aceitar os Termos de Uso e a Política de Privacidade."):
            self.assertContains(response, message, msg_prefix=message)
        # Valores digitados voltam escapados; senhas não voltam.
        self.assertContains(response, 'value="&lt;b&gt;x&lt;/b&gt;"')
        self.assertNotContains(response, "<b>x</b>")
        self.assertContains(response, 'value="nao-e-email"')
        self.assertNotContains(response, "fraca")

    def test_AC_5_injection_attempts_are_rejected_safely(self):
        for email in ("' OR 1=1 --@x.com", "a@b.com'; DROP TABLE auth_user;--", '"><script>alert(1)</script>@x.com'):
            response = self.client.post(SIGNUP_URL, signup_data(email=email))
            self.assertEqual(response.status_code, 200, email)
            self.assertNotContains(response, "<script>alert(1)</script>")
        response = self.client.post(SIGNUP_URL, signup_data(first_name="Robert'); DROP TABLE auth_user;--"))
        self.assertContains(response, "Use apenas letras, espaços, hífen ou apóstrofo.")
        self.assertEqual(User.objects.count(), 0)

    def test_AC_5_csrf_is_enforced(self):
        from django.test import Client

        response = Client(enforce_csrf_checks=True).post(SIGNUP_URL, signup_data())
        self.assertEqual(response.status_code, 403)
        self.assertEqual(User.objects.count(), 0)

    def test_AC_6_email_case_insensitive_on_server(self):
        User.objects.create_user("email@email.com", email="email@email.com", password="x")
        response = self.client.post(SIGNUP_URL, signup_data(email="eMaiL@EMAil.com"))
        self.assertContains(response, "Este e-mail já está cadastrado.")
        self.assertEqual(User.objects.count(), 1)

    def test_AC_7_successful_signup(self):
        response = self.client.post(SIGNUP_URL, signup_data(email=" Fulano@Exemplo.COM "), follow=True)
        self.assertRedirects(response, LOGIN_URL)
        self.assertContains(response, SUCCESS)
        user = User.objects.get()
        self.assertEqual((user.username, user.email), ("fulano@exemplo.com", "fulano@exemplo.com"))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertNotEqual(user.password, "Quarto#Azul42")
        self.assertNotIn("_auth_user_id", self.client.session)  # não inicia sessão

    def test_AC_9_google_button_has_no_action(self):
        response = self.client.get(SIGNUP_URL)
        self.assertContains(response, '<button type="button" data-google-signin')
        self.assertContains(response, 'title="Em breve"')

    def test_AC_10_legal_pages_are_public(self):
        for name, title in (("accounts:terms", "Termos de Uso"), ("accounts:privacy", "Política de Privacidade")):
            response = self.client.get(reverse(name))
            self.assertContains(response, title)
            self.assertContains(response, "Documento em elaboração.")
