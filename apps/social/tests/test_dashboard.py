from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import SocialAccount

from .helpers import VALID_META_SETTINGS


@override_settings(**VALID_META_SETTINGS)
class DashboardIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice", password="x")

    def setUp(self):
        self.client.force_login(self.user)

    def facebook(self):
        response = self.client.get(reverse("dashboard:index"))
        return next(p for p in response.context["platforms"] if p["name"] == "Facebook")

    def add(self, status):
        account = SocialAccount(owner=self.user, platform="facebook_page", external_id="1", name="X", status=status)
        account.set_token("t")
        account.save()

    def test_AC_15_not_connected_without_accounts(self):
        self.assertFalse(self.facebook()["connected"])

    def test_AC_15_connected_with_an_active_account(self):
        self.add(SocialAccount.Status.ACTIVE)
        self.assertTrue(self.facebook()["connected"])

    def test_AC_15_needs_reauth_does_not_count_as_connected(self):
        self.add(SocialAccount.Status.NEEDS_REAUTH)
        self.assertFalse(self.facebook()["connected"])

    def test_AC_15_other_users_accounts_do_not_count(self):
        other = get_user_model().objects.create_user("bob", password="x")
        account = SocialAccount(owner=other, platform="facebook_page", external_id="1", name="X")
        account.set_token("t")
        account.save()
        self.assertFalse(self.facebook()["connected"])

    def test_AC_15_other_indicators_remain_demonstrative(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertContains(response, "Dados demonstrativos")
