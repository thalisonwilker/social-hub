import logging
import re
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts import login_throttle as lt
from apps.accounts.models import LoginAttempt

from .helpers import LOGIN_URL, STRONG_PASSWORD, login_data

User = get_user_model()
PROFILE_SELECT = reverse("social:profile_select")
INVALID = "E-mail ou senha inválidos"
BAD_KEY = "Não foi possível processar o login. Recarregue a página e tente novamente."
DUPLICATE = "Esta tentativa de login já foi processada. Recarregue a página."
THROTTLED = "Muitas tentativas. Tente novamente em alguns minutos."


class LoginJourneyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("fulano@exemplo.com", email="fulano@exemplo.com", password=STRONG_PASSWORD)

    def post(self, email="fulano@exemplo.com", password=STRONG_PASSWORD, client=None, **kw):
        return (client or self.client).post(LOGIN_URL, login_data(email, password, **kw))

    # AC-1
    def test_AC_1_valid_login_redirects_and_rotates_session(self):
        self.client.get(LOGIN_URL)
        self.client.session.save()
        before = self.client.session.session_key
        response = self.post(email=" FULANO@Exemplo.com ")
        self.assertRedirects(response, PROFILE_SELECT, fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
        self.assertNotEqual(self.client.session.session_key, before)
        self.assertTrue(LoginAttempt.objects.get().succeeded)

    def test_AC_1_safe_next_is_followed_and_external_is_ignored(self):
        response = self.post(next="/contas/")
        self.assertRedirects(response, "/contas/", fetch_redirect_response=False)
        self.client.logout()
        response = self.post(next="https://evil.example.com/")
        self.assertRedirects(response, PROFILE_SELECT, fetch_redirect_response=False)

    # AC-2
    def test_AC_2_same_message_whether_or_not_the_account_exists(self):
        User.objects.create_user("inativo@x.com", email="inativo@x.com", password=STRONG_PASSWORD, is_active=False)
        bodies = []
        for email, password in (("fulano@exemplo.com", "Errada#123"), ("ninguem@exemplo.com", "Errada#123"),
                                ("inativo@x.com", STRONG_PASSWORD)):
            response = self.post(email=email, password=password)
            self.assertEqual(response.status_code, 401)
            self.assertContains(response, INVALID, status_code=401)
            self.assertNotContains(response, password, status_code=401)
            self.assertNotIn("_auth_user_id", self.client.session)
            body = response.content.decode().replace(email, "EMAIL")
            body = re.sub(r'value="[^"]*"', 'value=""', body)  # CSRF mascarado e chave mudam a cada resposta
            bodies.append(body)
        self.assertEqual(len(set(bodies)), 1)

    def test_AC_2_password_hash_runs_for_unknown_email(self):
        with mock.patch("django.contrib.auth.base_user.AbstractBaseUser.set_password") as set_password:
            self.post(email="ninguem@exemplo.com")
        set_password.assert_called_once()

    # AC-3
    def test_AC_3_invalid_fields_400_without_authenticating(self):
        with mock.patch("apps.accounts.views.authenticate") as auth:
            response = self.client.post(LOGIN_URL, {"email": "nao-e-email", "password": "", "chave_idempotencia": str(uuid.uuid4())})
        auth.assert_not_called()
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Informe um e-mail válido.", status_code=400)
        self.assertContains(response, "Informe sua senha.", status_code=400)
        self.assertEqual(LoginAttempt.objects.count(), 0)

    def test_AC_3_email_too_long(self):
        response = self.post(email="a" * 250 + "@x.com")
        self.assertContains(response, "Informe um e-mail válido.", status_code=400)

    # AC-5
    def test_AC_5_blocks_after_five_failures_even_with_right_password(self):
        for _ in range(5):
            self.assertEqual(self.post(password="Errada#123").status_code, 401)
        response = self.post()
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, THROTTLED, status_code=429)
        self.assertTrue(int(response["Retry-After"]) > 0)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(LoginAttempt.objects.count(), 5)  # bloqueio não grava tentativa

    def test_AC_5_field_errors_and_bad_keys_do_not_count(self):
        for _ in range(6):
            self.post(password="")
            self.post(key="nao-e-uuid")
        self.assertEqual(LoginAttempt.objects.count(), 0)
        self.assertRedirects(self.post(), PROFILE_SELECT, fetch_redirect_response=False)

    def test_AC_5_ip_limit(self):
        for i in range(20):
            self.post(email=f"u{i}@x.com", password="Errada#123")
        self.assertEqual(self.post().status_code, 429)
        other_ip = self.post(client=Client(REMOTE_ADDR="10.9.9.9"))
        self.assertEqual(other_ip.status_code, 302)

    def test_AC_5_email_is_stored_only_as_hash(self):
        self.post(password="Errada#123")
        attempt = LoginAttempt.objects.get()
        self.assertEqual(attempt.email_hash, lt.hash_email("fulano@exemplo.com"))
        self.assertNotIn("fulano", attempt.email_hash)

    # AC-6
    def test_AC_6_repeat_after_success_in_logged_browser_redirects_without_new_attempt(self):
        key = str(uuid.uuid4())
        self.post(key=key)
        response = self.post(key=key)
        self.assertRedirects(response, PROFILE_SELECT, fetch_redirect_response=False)
        self.assertEqual(LoginAttempt.objects.count(), 1)

    def test_AC_6_repeat_after_success_with_old_cookie_is_409_without_session(self):
        key = str(uuid.uuid4())
        self.post(key=key)
        other = Client()
        response = self.post(key=key, client=other)
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, DUPLICATE, status_code=409)
        self.assertNotIn("_auth_user_id", other.session)

    def test_AC_6_repeat_after_failure_is_401_and_does_not_count(self):
        key = str(uuid.uuid4())
        for _ in range(8):
            response = self.post(password="Errada#123", key=key)
            self.assertEqual(response.status_code, 401)
        self.assertEqual(LoginAttempt.objects.count(), 1)
        self.assertRedirects(self.post(), PROFILE_SELECT, fetch_redirect_response=False)

    def test_AC_6_repeat_after_failure_with_right_password_does_not_authenticate(self):
        key = str(uuid.uuid4())
        self.post(password="Errada#123", key=key)
        with mock.patch("apps.accounts.views.authenticate") as auth:
            response = self.post(key=key)
        auth.assert_not_called()
        self.assertEqual(response.status_code, 401)

    def test_AC_6_same_key_with_other_email_is_409(self):
        key = str(uuid.uuid4())
        self.post(password="Errada#123", key=key)
        response = self.post(email="outro@exemplo.com", key=key)
        self.assertEqual(response.status_code, 409)

    def test_AC_6_race_loser_does_not_create_session(self):
        """Duas requisições simultâneas: a outra grava a chave entre a leitura e a gravação desta."""
        key = str(uuid.uuid4())
        winner = LoginAttempt(key=uuid.UUID(key), email_hash=lt.hash_email("fulano@exemplo.com"), ip="127.0.0.1", succeeded=True)
        real_filter = LoginAttempt.objects.filter
        calls = {"n": 0}

        def filter_once_empty(*args, **kwargs):
            qs = real_filter(*args, **kwargs)
            if "key" in kwargs and calls["n"] == 0:
                calls["n"] += 1
                winner.save()
                return real_filter(pk=-1)  # esta requisição "não viu" a chave
            return qs

        with mock.patch.object(LoginAttempt.objects, "filter", side_effect=filter_once_empty):
            response = self.post(key=key)
        self.assertEqual(response.status_code, 409)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(LoginAttempt.objects.count(), 1)

    # AC-7
    def test_AC_7_missing_or_malformed_key_is_400(self):
        for key in (None, "", "123", str(uuid.uuid4()).upper().replace("-", "")):
            data = login_data("fulano@exemplo.com", STRONG_PASSWORD)
            if key is None:
                del data["chave_idempotencia"]
            else:
                data["chave_idempotencia"] = key
            response = self.client.post(LOGIN_URL, data)
            self.assertContains(response, BAD_KEY, status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_AC_7_page_has_server_fallback_key_and_script(self):
        response = self.client.get(LOGIN_URL)
        key = response.content.decode().split('name="chave_idempotencia" value="')[1].split('"')[0]
        self.assertIsNotNone(lt.parse_key(key))
        self.assertNotEqual(key, self.client.get(LOGIN_URL).content.decode().split('name="chave_idempotencia" value="')[1].split('"')[0])
        self.assertContains(response, "js/login.js")

    # AC-8 / AC-9 (marcação; o comportamento é verificado no UAT)
    def test_AC_8_loading_markup_and_signup_message(self):
        response = self.client.get(LOGIN_URL)
        for text in ('id="login-submit"', "data-loading", "data-submit-label", 'aria-live="polite"'):
            self.assertContains(response, text)

    def test_AC_9_google_and_forgot_password_without_action(self):
        response = self.client.get(LOGIN_URL)
        self.assertContains(response, '<button type="button" data-google-signin')
        # Spec 0016: "Esqueci minha senha" passou a levar à recuperação de senha.
        self.assertContains(response, f'href="{reverse("accounts:password_reset")}" data-forgot-password')
        self.assertContains(response, "Esqueci minha senha")

    # AC-10
    def test_AC_10_logs_have_no_sensitive_data(self):
        key = str(uuid.uuid4())
        with self.assertLogs("apps.accounts.login", level=logging.INFO) as logs:
            self.post(password="Errada#123", key=key)
            self.post(key=key)
            self.post(key=str(uuid.uuid4()))
        text = "\n".join(logs.output)
        for secret in ("Errada#123", STRONG_PASSWORD, "fulano@exemplo.com", "fulano", key, self.client.session.session_key):
            self.assertNotIn(secret, text)
        self.assertIn("login falha", text)
        self.assertIn("login sucesso", text)

    def test_authenticated_user_is_redirected(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(LOGIN_URL), PROFILE_SELECT, fetch_redirect_response=False)
