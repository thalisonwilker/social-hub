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


@override_settings(**VALID_META_SETTINGS)
class DashboardThreadsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice", password="x")

    def setUp(self):
        self.client.force_login(self.user)

    def platform(self, name):
        response = self.client.get(reverse("dashboard:index"))
        return next(p for p in response.context["platforms"] if p["name"] == name)

    def add_threads(self, owner=None, status=SocialAccount.Status.ACTIVE, expires_in_days=30):
        from datetime import timedelta

        from django.utils import timezone

        account = SocialAccount(
            owner=owner or self.user, platform="threads", external_id="900", name="Maria", username="maria", status=status,
            token_expires_at=timezone.now() + timedelta(days=expires_in_days),
        )
        account.set_token("t")
        account.save()
        return account

    def test_AC_24_threads_is_not_connected_without_a_profile(self):
        """AC-24: sem perfil do Threads, o card mostra Não conectado."""
        self.assertFalse(self.platform("Threads")["connected"])

    def test_AC_24_threads_is_connected_with_an_active_profile(self):
        """AC-24: com perfil ativo, o Threads aparece como Conectado (e o Facebook não é afetado)."""
        self.add_threads()
        self.assertTrue(self.platform("Threads")["connected"])
        self.assertFalse(self.platform("Facebook")["connected"])

    def test_AC_24_needs_reauth_and_expired_tokens_do_not_count(self):
        """AC-24: Reconexão necessária ou token vencido não contam como conectado."""
        account = self.add_threads(status=SocialAccount.Status.NEEDS_REAUTH)
        self.assertFalse(self.platform("Threads")["connected"])
        account.status = SocialAccount.Status.ACTIVE
        account.token_expires_at = account.token_expires_at.replace(year=2000)
        account.save()
        self.assertFalse(self.platform("Threads")["connected"])  # a expiração é refletida localmente

    def test_AC_24_other_users_profiles_do_not_count(self):
        """AC-24: perfil de outro usuário não conta."""
        other = get_user_model().objects.create_user("bob", password="x")
        self.add_threads(owner=other)
        self.assertFalse(self.platform("Threads")["connected"])
