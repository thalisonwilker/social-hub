"""Spec 0016 — recuperação de senha."""

import logging
import re
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts import password_reset as pr
from apps.accounts.models import PasswordResetRequest, PasswordResetToken

User = get_user_model()
REQUEST_URL = reverse("accounts:password_reset")
CONFIRM_URL = reverse("accounts:password_reset_confirm")
LOGIN_URL = reverse("accounts:login")
GENERIC = "Se o e-mail estiver cadastrado, você receberá instruções para redefinir sua senha."
INVALID_LINK = "Este link de redefinição é inválido ou expirou. Solicite um novo."
DONE = "Sua senha foi redefinida. Faça login com a nova senha."
NEW_PASSWORD = "Nova#Senha2026"
OLD_PASSWORD = "Antiga#Senha1"


def ask(client, email, key=None, **extra):
    return client.post(REQUEST_URL, {"email": email, "chave_idempotencia": key or str(uuid.uuid4()), **extra})


def token_from_outbox(index=-1):
    return re.search(r"\?token=([\w-]+)", mail.outbox[index].body).group(1)


class PasswordResetTests(TestCase):
    def test_AC_10_post_with_browser_origin_passes_csrf(self):
        """Regressão do UAT: POST com Origin do próprio site e CSRF ligado."""
        client = Client(enforce_csrf_checks=True)
        ask(Client(), "ana@exemplo.com")
        client.get(CONFIRM_URL, {"token": token_from_outbox()})
        page = client.get(CONFIRM_URL)
        csrf = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode()).group(1)
        response = client.post(
            CONFIRM_URL,
            {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD, "csrfmiddlewaretoken": csrf},
            HTTP_ORIGIN="http://testserver",
        )
        self.assertRedirects(response, LOGIN_URL, fetch_redirect_response=False)

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ana@exemplo.com", email="ana@exemplo.com", password=OLD_PASSWORD)

    def open_link(self, client=None, token=None):
        client = client or self.client
        return client.get(CONFIRM_URL, {"token": token or token_from_outbox()})

    def reset(self, password=NEW_PASSWORD, confirm=None, client=None):
        return (client or self.client).post(CONFIRM_URL, {"password1": password, "password2": confirm or password})

    # AC-1
    def test_AC_1_request_page(self):
        response = self.client.get(REQUEST_URL)
        for text in ('name="email"', 'name="chave_idempotencia"', "Enviar instruções", "Voltar para o login",
                     "js/password_reset.js", 'aria-live="polite"'):
            self.assertContains(response, text, msg_prefix=text)
        self.assertContains(self.client.get(LOGIN_URL), f'href="{REQUEST_URL}"')

    # AC-2
    def test_AC_2_invalid_email_400_nothing_recorded(self):
        for email in ("", "nao-e-email", "a@b.c"):
            response = ask(self.client, email)
            self.assertContains(response, "Informe um e-mail válido.", status_code=400)
            self.assertContains(response, 'aria-invalid="true"', status_code=400)
        self.assertEqual(PasswordResetRequest.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_AC_2_bad_key_400(self):
        response = ask(self.client, "ana@exemplo.com", key="123")
        self.assertContains(response, "Recarregue a página", status_code=400)
        self.assertEqual(len(mail.outbox), 0)

    # AC-3
    def test_AC_3_same_public_answer_with_or_without_account(self):
        User.objects.create_user("inativo@x.com", email="inativo@x.com", password="x", is_active=False)
        bodies = []
        for email in ("  ANA@exemplo.com ", "ninguem@exemplo.com", "inativo@x.com", "ana@exemplo.com"):
            client = Client()
            response = ask(client, email)
            self.assertRedirects(response, REQUEST_URL, fetch_redirect_response=False)
            page = client.get(REQUEST_URL)
            self.assertContains(page, GENERIC)
            bodies.append(re.sub(r'value="[^"]*"', 'value=""', page.content.decode()))
        self.assertEqual(len(set(bodies)), 1)
        self.assertEqual(len(mail.outbox), 1)  # só a 1ª (conta ativa); a 4ª barrada pelo limite da conta
        self.assertEqual(mail.outbox[0].to, ["ana@exemplo.com"])

    def test_AC_3_email_is_sent_outside_the_request_when_async(self):
        with override_settings(ACCOUNTS_EMAIL_ASYNC=True), mock.patch("apps.accounts.emails.threading.Thread") as thread:
            ask(self.client, "ana@exemplo.com")
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()
        self.assertEqual(len(mail.outbox), 0)

    # AC-4
    @override_settings(PUBLIC_BASE_URL="https://hub.exemplo.com")
    def test_AC_4_email_with_secure_link_and_only_hash_stored(self):
        ask(self.client, "ana@exemplo.com")
        message = mail.outbox[0]
        token = token_from_outbox()
        self.assertIn(f"https://hub.exemplo.com{CONFIRM_URL}?token={token}", message.body)
        self.assertIn("30 minutos", message.body)
        self.assertIn("Se não foi você, ignore este e-mail", message.body)
        self.assertGreaterEqual(len(token), 43)  # 32 bytes em base64url
        stored = PasswordResetToken.objects.get()
        self.assertEqual(stored.token_hash, pr.hash_token(token))
        self.assertNotIn(token, str(PasswordResetToken.objects.values().get()))
        self.assertAlmostEqual((stored.expires_at - stored.created_at).total_seconds(), 30 * 60, delta=1)

    def test_AC_4_new_request_invalidates_previous_link(self):
        ask(self.client, "ana@exemplo.com")
        first = token_from_outbox()
        PasswordResetToken.objects.update(created_at=timezone.now() - timedelta(hours=2))  # fora do limite
        ask(self.client, "ana@exemplo.com")
        self.assertEqual(len(mail.outbox), 2)
        self.assertContains(self.open_link(token=first), INVALID_LINK, status_code=400)
        self.assertRedirects(self.open_link(), CONFIRM_URL, fetch_redirect_response=False)

    # AC-5
    def test_AC_5_same_key_does_not_send_again(self):
        key = str(uuid.uuid4())
        for _ in range(3):
            self.assertRedirects(ask(self.client, "ana@exemplo.com", key=key), REQUEST_URL, fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(PasswordResetRequest.objects.count(), 1)
        self.assertEqual(PasswordResetToken.objects.count(), 1)

    # AC-6
    def test_AC_6_ip_limit_429(self):
        for i in range(5):
            ask(self.client, f"u{i}@exemplo.com")
        response = ask(self.client, "ana@exemplo.com")
        self.assertContains(response, "Muitas solicitações", status_code=429)
        self.assertTrue(int(response["Retry-After"]) > 0)
        self.assertEqual(len(mail.outbox), 0)
        other = ask(Client(REMOTE_ADDR="10.1.1.1"), "ana@exemplo.com")
        self.assertEqual(other.status_code, 302)

    def test_AC_6_account_limit_is_silent(self):
        ask(Client(REMOTE_ADDR="10.0.0.1"), "ana@exemplo.com")
        response = ask(Client(REMOTE_ADDR="10.0.0.2"), "ana@exemplo.com")
        self.assertRedirects(response, REQUEST_URL, fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        PasswordResetToken.objects.update(created_at=timezone.now() - timedelta(minutes=61))
        ask(Client(REMOTE_ADDR="10.0.0.3"), "ana@exemplo.com")
        self.assertEqual(len(mail.outbox), 2)

    def test_AC_6_invalid_requests_do_not_count(self):
        for _ in range(6):
            ask(self.client, "nao-e-email")
            ask(self.client, "ana@exemplo.com", key="x")
        self.assertEqual(ask(self.client, "ana@exemplo.com").status_code, 302)

    # AC-7
    def test_AC_7_opening_link_stores_reference_and_cleans_url(self):
        ask(self.client, "ana@exemplo.com")
        token = token_from_outbox()
        response = self.open_link(token=token)
        self.assertRedirects(response, CONFIRM_URL, fetch_redirect_response=False)
        self.assertEqual(response["Referrer-Policy"], "no-referrer")
        self.assertEqual(self.client.session[pr.SESSION_KEY], PasswordResetToken.objects.get().pk)
        self.assertNotIn(token, str(dict(self.client.session)))
        page = self.client.get(CONFIRM_URL)
        # O formulário não pode ter `no-referrer`: o navegador mandaria `Origin: null` e o CSRF recusaria.
        self.assertNotEqual(page.get("Referrer-Policy"), "no-referrer")
        for text in ('name="password1"', 'name="password2"', "Redefinir senha", "data-password-toggle", "Voltar para o login"):
            self.assertContains(page, text, msg_prefix=text)

    # AC-8
    def test_AC_8_invalid_expired_used_or_stale_links(self):
        self.assertContains(self.open_link(token="inexistente"), INVALID_LINK, status_code=400)
        self.assertContains(self.client.get(CONFIRM_URL), INVALID_LINK, status_code=400)
        ask(self.client, "ana@exemplo.com")
        token = token_from_outbox()
        PasswordResetToken.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.open_link(token=token)
        self.assertContains(response, INVALID_LINK, status_code=400)
        self.assertNotContains(response, 'name="password1"', status_code=400)

    def test_AC_8_password_changed_elsewhere_kills_link(self):
        ask(self.client, "ana@exemplo.com")
        self.open_link()
        self.user.set_password("Outra#Senha9")
        self.user.save()
        self.assertContains(self.reset(), INVALID_LINK, status_code=400)

    # AC-9
    def test_AC_9_policy_and_mismatch_do_not_consume_token(self):
        ask(self.client, "ana@exemplo.com")
        self.open_link()
        response = self.reset(password="fraca")
        self.assertContains(response, "A senha precisa de pelo menos uma letra maiúscula.", status_code=400)
        response = self.reset(password=NEW_PASSWORD, confirm="Outra#Senha2026")
        self.assertContains(response, "As senhas não coincidem.", status_code=400)
        response = self.reset(password="Ana@exemplo.com1")  # parecida com o e-mail
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(PasswordResetToken.objects.get().used_at)
        self.assertRedirects(self.reset(), LOGIN_URL, fetch_redirect_response=False)

    # AC-10
    def test_AC_10_single_use_and_no_auto_login(self):
        ask(self.client, "ana@exemplo.com")
        token = token_from_outbox()
        self.open_link(token=token)
        response = self.reset()
        self.assertRedirects(response, LOGIN_URL, fetch_redirect_response=False)
        self.assertContains(self.client.get(LOGIN_URL), DONE)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertTrue(self.user.password.startswith("pbkdf2_") or "$" in self.user.password)
        self.assertContains(self.open_link(token=token), INVALID_LINK, status_code=400)

    def test_AC_10_parallel_submit_only_one_wins(self):
        ask(self.client, "ana@exemplo.com")
        token = token_from_outbox()
        other = Client()
        self.open_link(token=token)
        self.open_link(client=other, token=token)
        with mock.patch("apps.accounts.password_reset.consume", side_effect=[True, False]):
            first = self.reset()
            second = self.reset(password="Terceira#Senha3", client=other)
        self.assertEqual(first.status_code, 302)
        self.assertContains(second, INVALID_LINK, status_code=400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_AC_10_consume_is_conditional(self):
        ask(self.client, "ana@exemplo.com")
        stored = PasswordResetToken.objects.get()
        self.assertTrue(pr.consume(stored))
        self.assertFalse(pr.consume(stored))

    # AC-11
    def test_AC_11_sessions_are_revoked(self):
        other = Client()
        other.force_login(self.user)
        self.assertEqual(other.get(reverse("accounts:profile")).status_code, 200)
        ask(self.client, "ana@exemplo.com")
        self.open_link()
        self.reset()
        user_sessions = [s for s in Session.objects.all() if s.get_decoded().get("_auth_user_id") == str(self.user.pk)]
        self.assertEqual(user_sessions, [])
        self.assertEqual(other.get(reverse("accounts:profile")).status_code, 302)

    # AC-12
    def test_AC_12_password_changed_notice(self):
        ask(self.client, "ana@exemplo.com")
        token = token_from_outbox()
        self.open_link(token=token)
        self.reset()
        notice = mail.outbox[-1]
        self.assertEqual(notice.subject, "Sua senha do Social Hub foi alterada")
        self.assertEqual(notice.to, ["ana@exemplo.com"])
        self.assertNotIn("token=", notice.body)
        self.assertNotIn(NEW_PASSWORD, notice.body)
        self.assertIn("peça uma nova recuperação", notice.body)

    def test_AC_12_smtp_failure_is_logged_without_content(self):
        with mock.patch("apps.accounts.emails.send_mail", side_effect=OSError("smtp down")), \
             self.assertLogs("apps.accounts.emails", level=logging.WARNING) as logs:
            response = ask(self.client, "ana@exemplo.com")
        self.assertEqual(response.status_code, 302)
        self.assertIn("email link falhou (OSError)", logs.output[0])

    # AC-13
    def test_AC_13_loading_markup(self):
        self.assertContains(self.client.get(REQUEST_URL), 'data-busy-label="Enviando…"')
        ask(self.client, "ana@exemplo.com")
        self.open_link()
        self.assertContains(self.client.get(CONFIRM_URL), 'data-busy-label="Redefinindo…"')

    # AC-14
    def test_AC_14_logs_have_no_secrets(self):
        with self.assertLogs("apps.accounts", level=logging.INFO) as logs:
            ask(self.client, "ana@exemplo.com")
            token = token_from_outbox()
            self.open_link(token=token)
            self.reset()
            ask(self.client, "ninguem@exemplo.com")
        text = "\n".join(logs.output)
        for secret in (token, NEW_PASSWORD, "ana@exemplo.com", "ninguem", pr.hash_token(token)):
            self.assertNotIn(secret, text)
        self.assertIn("recuperacao aceito", text)
        self.assertIn("recuperacao senha_redefinida", text)

    def test_AC_14_runserver_log_drops_query_string(self):
        from apps.core.log_filters import StripQueryString

        record = logging.LogRecord("django.server", logging.INFO, __file__, 1, '"%s" %s %s',
                                   ("GET /redefinir-senha/?token=SEGREDO HTTP/1.1", "302", "0"), None)
        StripQueryString().filter(record)
        self.assertNotIn("SEGREDO", record.getMessage())
        self.assertIn("GET /redefinir-senha/ HTTP/1.1", record.getMessage())

    def test_AC_14_retention(self):
        ask(self.client, "ana@exemplo.com")
        PasswordResetRequest.objects.update(created_at=timezone.now() - timedelta(hours=25))
        PasswordResetToken.objects.update(expires_at=timezone.now() - timedelta(hours=25))
        pr.purge_old()
        self.assertEqual((PasswordResetRequest.objects.count(), PasswordResetToken.objects.count()), (0, 0))

    def test_signup_account_without_email_field_receives_at_username(self):
        User.objects.create_user("bia@exemplo.com", password=OLD_PASSWORD)
        ask(self.client, "BIA@exemplo.com")
        self.assertEqual(mail.outbox[-1].to, ["bia@exemplo.com"])
