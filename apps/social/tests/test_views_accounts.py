from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import SocialAccount
from apps.social.services.meta import GraphClient, MetaApiError

from .helpers import PAGE_TOKEN_1, VALID_META_SETTINGS


def make_account(owner, external_id="1", name="Loja", **kwargs):
    account = SocialAccount(owner=owner, platform="facebook_page", external_id=external_id, name=name, **kwargs)
    account.set_token(PAGE_TOKEN_1)
    account.save()
    return account


@override_settings(**VALID_META_SETTINGS)
class AccountsViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice", password="x")
        cls.bob = User.objects.create_user("bob", password="x")

    def setUp(self):
        self.client.force_login(self.alice)

    # ---- AC-1 ------------------------------------------------------------
    @override_settings(META_APP_SECRET="")
    def test_AC_1_page_warns_and_disables_button_when_not_configured(self):
        response = self.client.get(reverse("social:accounts"))
        self.assertContains(response, "Integração com a Meta não configurada")
        self.assertContains(response, "disabled")

    # ---- AC-11 -----------------------------------------------------------
    def test_AC_11_empty_state(self):
        response = self.client.get(reverse("social:accounts"))
        self.assertContains(response, "Nenhuma conta conectada")

    def test_AC_11_lists_only_own_accounts_without_tokens(self):
        mine = make_account(self.alice, "1", "Minha Loja", category="Varejo")
        make_account(self.bob, "2", "Loja do Bob")
        make_account(self.alice, "3", "Precisa Reconectar", status=SocialAccount.Status.NEEDS_REAUTH)
        response = self.client.get(reverse("social:accounts"))
        self.assertContains(response, "Minha Loja")
        self.assertNotContains(response, "Loja do Bob")
        self.assertContains(response, "Ativa")
        self.assertContains(response, "Reconexão necessária")
        self.assertContains(response, "Verificar")
        self.assertContains(response, "Desconectar")
        self.assertNotContains(response, PAGE_TOKEN_1)
        self.assertNotContains(response, mine.access_token_enc)

    # ---- AC-12 -----------------------------------------------------------
    def check(self, account):
        return self.client.post(reverse("social:account_check", args=[account.pk]), follow=True)

    def test_AC_12_ok_keeps_active_and_updates_last_checked(self):
        account = make_account(self.alice, status=SocialAccount.Status.NEEDS_REAUTH, last_error="x")
        with mock.patch.object(GraphClient, "get_page", return_value={"id": "1"}) as m:
            response = self.check(account)
        m.assert_called_once_with("1", PAGE_TOKEN_1)
        account.refresh_from_db()
        self.assertEqual(account.status, SocialAccount.Status.ACTIVE)
        self.assertEqual(account.last_error, "")
        self.assertIsNotNone(account.last_checked_at)
        self.assertContains(response, "conectada e funcionando")

    def test_AC_12_token_error_marks_needs_reauth(self):
        account = make_account(self.alice)
        with mock.patch.object(GraphClient, "get_page", side_effect=MetaApiError("x", code=190)):
            response = self.check(account)
        account.refresh_from_db()
        self.assertEqual(account.status, SocialAccount.Status.NEEDS_REAUTH)
        self.assertEqual(account.last_error, "Meta erro 190")
        self.assertIsNotNone(account.last_checked_at)
        self.assertContains(response, "Reconexão necessária")

    def test_AC_12_other_errors_keep_status(self):
        for error in (MetaApiError("x", code=4), MetaApiError("x", code="network")):
            with self.subTest(code=error.code):
                account = make_account(self.alice, external_id=f"e{error.code}")
                with mock.patch.object(GraphClient, "get_page", side_effect=error):
                    response = self.check(account)
                account.refresh_from_db()
                self.assertEqual(account.status, SocialAccount.Status.ACTIVE)
                self.assertContains(response, "Não foi possível verificar agora")

    # ---- AC-13 -----------------------------------------------------------
    def test_AC_13_disconnect_deletes_account_and_token(self):
        account = make_account(self.alice)
        response = self.client.post(reverse("social:account_disconnect", args=[account.pk]), follow=True)
        self.assertRedirects(response, reverse("social:accounts"))
        self.assertContains(response, "foi desconectada")
        self.assertFalse(SocialAccount.objects.filter(pk=account.pk).exists())

    def test_AC_13_disconnect_form_asks_for_confirmation(self):
        make_account(self.alice)
        self.assertContains(self.client.get(reverse("social:accounts")), "data-confirm=")

    def test_AC_13_actions_reject_get(self):
        account = make_account(self.alice)
        for name in ("social:account_disconnect", "social:account_check"):
            self.assertEqual(self.client.get(reverse(name, args=[account.pk])).status_code, 405)
        self.assertTrue(SocialAccount.objects.filter(pk=account.pk).exists())

    # ---- AC-14 / AC-17 ---------------------------------------------------
    def test_AC_14_other_users_cannot_check_or_disconnect(self):
        account = make_account(self.bob, "9", "Do Bob")
        for name in ("social:account_check", "social:account_disconnect"):
            with self.subTest(name):
                self.assertEqual(self.client.post(reverse(name, args=[account.pk])).status_code, 404)
        account.refresh_from_db()
        self.assertEqual(account.status, SocialAccount.Status.ACTIVE)

    def test_AC_17_anonymous_is_redirected_to_login(self):
        account = make_account(self.alice)
        self.client.logout()
        for name, args, method in (("social:accounts", [], "get"), ("social:account_check", [account.pk], "post"),
                                    ("social:account_disconnect", [account.pk], "post")):
            with self.subTest(name):
                url = reverse(name, args=args)
                response = getattr(self.client, method)(url)
                self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}", fetch_redirect_response=False)
        self.assertTrue(SocialAccount.objects.filter(pk=account.pk).exists())
