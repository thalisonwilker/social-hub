import logging
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.social.models import SocialAccount
from apps.social.services import threads_tokens
from apps.social.services.meta import MetaApiError

from .threads_helpers import THREADS_SETTINGS, make_threads_account

NOW = timezone.now()


@override_settings(**THREADS_SETTINGS)
class EnsureFreshTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice", password="x")

    def fake_client(self, **kwargs):
        client = mock.Mock()
        client.refresh_token.return_value = kwargs.get("result", {"access_token": "token-renovado", "expires_in": 5184000})
        if "error" in kwargs:
            client.refresh_token.side_effect = kwargs["error"]
        return client

    def account(self, **kwargs):
        acc = make_threads_account(self.alice, **kwargs)
        acc.token_expires_at = NOW + timedelta(days=kwargs.get("days_left", 60))
        acc.token_refreshed_at = NOW - timedelta(hours=kwargs.get("refreshed_hours_ago", 48))
        acc.save()
        return acc

    def run_ensure(self, acc, client):
        return threads_tokens.ensure_fresh(acc, client=client, now=NOW)

    def test_AC_12_expired_token_marks_needs_reauth_without_network(self):
        """AC-12: token já expirado → needs_reauth e nenhuma chamada à rede."""
        acc = self.account(days_left=-1)
        client = self.fake_client()
        self.assertFalse(self.run_ensure(acc, client))
        acc.refresh_from_db()
        self.assertEqual(acc.status, SocialAccount.Status.NEEDS_REAUTH)
        client.refresh_token.assert_not_called()

    def test_AC_12_far_from_expiry_does_nothing(self):
        """AC-12: com 30 dias ou mais restantes não chama th_refresh_token (inclusive no limite exato)."""
        for days in (45, 30):
            acc = self.account(days_left=days, external_id=f"d{days}")
            client = self.fake_client()
            self.assertTrue(self.run_ensure(acc, client))
            client.refresh_token.assert_not_called()

    def test_AC_12_too_young_token_is_not_refreshed(self):
        """AC-12: faltam menos de 30 dias mas o token tem menos de 24 h → nada a fazer."""
        acc = self.account(days_left=10, refreshed_hours_ago=23)
        client = self.fake_client()
        self.assertTrue(self.run_ensure(acc, client))
        client.refresh_token.assert_not_called()

    def test_AC_12_due_token_is_refreshed_and_validity_restarts(self):
        """AC-12: faltam < 30 dias e idade ≥ 24 h → renova; novo token cifrado, expiração +60 dias, refreshed_at agora."""
        acc = self.account(days_left=10, refreshed_hours_ago=24, token="token-antigo")
        client = self.fake_client()
        self.assertTrue(self.run_ensure(acc, client))
        client.refresh_token.assert_called_once_with("token-antigo")
        acc.refresh_from_db()
        self.assertEqual(acc.get_token(), "token-renovado")
        self.assertNotIn("token-renovado", acc.access_token_enc)
        self.assertEqual(acc.token_expires_at, NOW + timedelta(seconds=5184000))
        self.assertEqual(acc.token_refreshed_at, NOW)
        self.assertEqual(acc.status, SocialAccount.Status.ACTIVE)

    def test_AC_12_token_error_during_refresh_marks_needs_reauth(self):
        """AC-12: erro de token (190) na renovação → needs_reauth."""
        acc = self.account(days_left=5)
        self.assertFalse(self.run_ensure(acc, self.fake_client(error=MetaApiError("x", code=190))))
        acc.refresh_from_db()
        self.assertEqual((acc.status, acc.last_error), (SocialAccount.Status.NEEDS_REAUTH, "Meta erro 190"))

    def test_AC_12_other_errors_keep_the_current_token_and_proceed(self):
        """AC-12: outro erro (rede, limite) → mantém o token atual e segue."""
        for error in (MetaApiError("x", code="network"), MetaApiError("x", code=4, status=429)):
            acc = self.account(days_left=5, token="token-atual", external_id=f"e{error.code}")
            self.assertTrue(self.run_ensure(acc, self.fake_client(error=error)))
            acc.refresh_from_db()
            self.assertEqual(acc.get_token(), "token-atual")
            self.assertEqual(acc.status, SocialAccount.Status.ACTIVE)

    def test_AC_12_tokens_that_do_not_expire_are_ignored(self):
        """AC-12: contas sem validade (Páginas do Facebook) não passam por renovação."""
        page = SocialAccount(owner=self.alice, platform="facebook_page", external_id="1", name="P")
        page.set_token("t")
        page.save()
        client = self.fake_client()
        self.assertTrue(self.run_ensure(page, client))
        client.refresh_token.assert_not_called()

    @override_settings(THREADS_REFRESH_WINDOW_DAYS=7)
    def test_AC_12_window_is_configurable(self):
        """AC-12: a janela vem de THREADS_REFRESH_WINDOW_DAYS."""
        acc = self.account(days_left=10)
        client = self.fake_client()
        self.run_ensure(acc, client)
        client.refresh_token.assert_not_called()  # 10 dias restantes > janela de 7

    def test_AC_25_logs_never_contain_tokens(self):
        """AC-25: os logs de renovação/expiração não trazem tokens."""
        acc = self.account(days_left=5, token="token-secreto-xyz")
        with self.assertLogs("apps.social.meta", level=logging.INFO) as logs:
            self.run_ensure(acc, self.fake_client())
            expired = self.account(days_left=-2, token="outro-segredo", external_id="x")
            self.run_ensure(expired, self.fake_client())
        output = "\n".join(logs.output)
        for secret in ("token-secreto-xyz", "token-renovado", "outro-segredo"):
            self.assertNotIn(secret, output)
        self.assertIn("threads_token_refreshed", output)
        self.assertIn("threads_token_expired", output)
