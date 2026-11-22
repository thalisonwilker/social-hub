from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import SocialAccount
from apps.social.services.meta import GraphClient, MetaApiError

from .helpers import VALID_META_SETTINGS
from .test_instagram_model import make_instagram, make_page

IG = SocialAccount.Platform.INSTAGRAM


@override_settings(**VALID_META_SETTINGS)
class InstagramAccountsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user("alice", password="x")
        cls.other = User.objects.create_user("bob", password="x")

    def setUp(self):
        self.client.force_login(self.user)
        self.page = make_page(self.user)
        self.ig = make_instagram(self.user, self.page)

    def test_AC_5_disconnecting_the_page_removes_its_instagram(self):
        self.client.post(reverse("social:account_disconnect", args=[self.page.pk]))
        self.assertFalse(SocialAccount.objects.filter(pk__in=[self.page.pk, self.ig.pk]).exists())

    def test_AC_5_disconnecting_only_instagram_keeps_the_page(self):
        self.client.post(reverse("social:account_disconnect", args=[self.ig.pk]))
        self.assertFalse(SocialAccount.objects.filter(pk=self.ig.pk).exists())
        self.assertTrue(SocialAccount.objects.filter(pk=self.page.pk).exists())

    def test_AC_5_only_the_owner_can_disconnect(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("social:account_disconnect", args=[self.ig.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(SocialAccount.objects.filter(pk=self.ig.pk).exists())

    def test_AC_5_accounts_page_lists_instagram_with_its_page(self):
        html = self.client.get(reverse("social:accounts")).content.decode()
        self.assertIn("@loja", html)
        self.assertIn("via Página Loja", html)
        self.assertNotIn("page-token", html)  # AC-21

    def test_AC_21_verify_ok_uses_the_parent_page(self):
        with mock.patch.object(GraphClient, "get_page", return_value={"id": "1"}) as get_page, \
             mock.patch.object(GraphClient, "get_followers_count", return_value=None):  # spec 0017
            self.client.post(reverse("social:account_check", args=[self.ig.pk]))
        self.assertEqual(get_page.call_args.args[0], self.page.external_id)

    def test_AC_19_verify_token_error_marks_both_accounts(self):
        error = MetaApiError("x", code=190)
        with mock.patch.object(GraphClient, "get_page", side_effect=error):
            self.client.post(reverse("social:account_check", args=[self.ig.pk]))
        for account in (self.ig, self.page):
            account.refresh_from_db()
            self.assertEqual(account.status, SocialAccount.Status.NEEDS_REAUTH)
