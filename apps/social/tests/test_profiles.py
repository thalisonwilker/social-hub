"""Spec 0011 — perfis, seleção, wizard, escopo e login."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import Profile, SocialAccount
from apps.social.services import profiles
from apps.social.services.threads import ThreadsClient

from .helpers import VALID_META_SETTINGS

User = get_user_model()


def make_account(user, profile=None, external_id="1", platform="facebook_page", name="Página"):
    account = SocialAccount(owner=user, profile=profile, platform=platform, external_id=external_id, name=name)
    account.set_token("t")
    account.save()
    return account


@override_settings(**VALID_META_SETTINGS)
class ProfilesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("alice", password="pw12345!")
        cls.other = User.objects.create_user("bob", password="pw12345!")

    def setUp(self):
        self.client.force_login(self.user)

    def test_AC_1_login_goes_to_profile_select(self):
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {"username": "alice", "password": "pw12345!"})
        self.assertRedirects(response, reverse("social:profile_select"), fetch_redirect_response=False)
        self.assertNotIn(profiles.ACTIVE_KEY, self.client.session)

    def test_AC_1_opening_the_selector_clears_the_active_profile(self):
        profile = Profile.objects.create(owner=self.user, name="A")
        self.client.post(reverse("social:profile_enter", args=[profile.pk]))
        self.assertIn(profiles.ACTIVE_KEY, self.client.session)
        self.client.get(reverse("social:profile_select"))
        self.assertNotIn(profiles.ACTIVE_KEY, self.client.session)

    def test_AC_1_login_signal_clears_the_active_profile(self):
        from django.contrib.auth.signals import user_logged_in

        request = mock.Mock(session={profiles.ACTIVE_KEY: 5, profiles.WIZARD_KEY: 5})
        user_logged_in.send(sender=User, request=request, user=self.user)
        self.assertEqual(request.session, {})

    def test_AC_2_without_profiles_only_the_plus(self):
        response = self.client.get(reverse("social:profile_select"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("social:profile_new"))
        self.assertNotContains(response, "/entrar/")
        self.assertContains(response, "Novo perfil")

    def test_AC_3_enter_profile_activates_and_goes_to_dashboard(self):
        profile = Profile.objects.create(owner=self.user, name="Loja")
        response = self.client.post(reverse("social:profile_enter", args=[profile.pk]))
        self.assertRedirects(response, reverse("dashboard:index"))
        self.assertEqual(self.client.session[profiles.ACTIVE_KEY], profile.pk)

    def test_AC_3_select_lists_profiles(self):
        Profile.objects.create(owner=self.user, name="Loja")
        self.assertContains(self.client.get(reverse("social:profile_select")), "Loja")

    def test_AC_3_enter_requires_post(self):
        profile = Profile.objects.create(owner=self.user, name="Loja")
        self.assertEqual(self.client.get(reverse("social:profile_enter", args=[profile.pk])).status_code, 405)

    def test_AC_4_wizard_name_creates_and_goes_to_connect(self):
        response = self.client.post(reverse("social:profile_new"), {"name": "  Minha loja "})
        profile = Profile.objects.get(owner=self.user)
        self.assertEqual(profile.name, "Minha loja")
        self.assertRedirects(response, reverse("social:profile_connect", args=[profile.pk]))
        self.assertEqual(self.client.session[profiles.ACTIVE_KEY], profile.pk)

    def test_AC_4_blank_name_is_rejected(self):
        response = self.client.post(reverse("social:profile_new"), {"name": "   "})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Profile.objects.exists())

    def test_AC_4_duplicate_name_is_rejected_case_insensitive(self):
        Profile.objects.create(owner=self.user, name="Loja")
        response = self.client.post(reverse("social:profile_new"), {"name": "loja"})
        self.assertContains(response, "já tem um perfil")
        self.assertEqual(Profile.objects.filter(owner=self.user).count(), 1)

    def test_AC_4_same_name_allowed_for_other_user(self):
        Profile.objects.create(owner=self.other, name="Loja")
        self.client.post(reverse("social:profile_new"), {"name": "Loja"})
        self.assertTrue(Profile.objects.filter(owner=self.user, name="Loja").exists())

    def test_AC_5_connect_step_shows_networks(self):
        profile = Profile.objects.create(owner=self.user, name="Loja")
        response = self.client.get(reverse("social:profile_connect", args=[profile.pk]))
        for label in ("Facebook", "Instagram", "Threads", "WhatsApp", "Twitter / X", "TikTok"):
            self.assertContains(response, label)
        self.assertContains(response, "Em breve")
        self.assertContains(response, reverse("social:facebook_connect"))

    @override_settings(THREADS_APP_ID="1", THREADS_APP_SECRET="s", THREADS_REDIRECT_URI="http://localhost:8080/contas/threads/callback/")
    def test_AC_6_threads_connection_links_to_profile_and_goes_to_dashboard(self):
        profile = Profile.objects.create(owner=self.user, name="Loja")
        self.client.get(reverse("social:profile_connect", args=[profile.pk]))
        session = self.client.session
        from apps.social.services import threads_connect

        session[threads_connect.STATE_KEY] = "st"
        session.save()
        with mock.patch("apps.social.services.facebook_connect.consume_state", return_value=True), mock.patch(
            "apps.social.services.threads_connect.connect_profile",
            side_effect=lambda user, code: make_account(user, None, "9", "threads", "Th"),
        ):
            response = self.client.get(reverse("social:threads_callback"), {"code": "c", "state": "st"})
        self.assertRedirects(response, reverse("dashboard:index"), fetch_redirect_response=False)
        self.assertEqual(SocialAccount.objects.get(external_id="9").profile, profile)

    def test_AC_6_failure_returns_to_wizard_step(self):
        profile = Profile.objects.create(owner=self.user, name="Loja")
        self.client.get(reverse("social:profile_connect", args=[profile.pk]))
        response = self.client.get(reverse("social:facebook_callback"), {"error": "access_denied"})
        self.assertRedirects(response, reverse("social:profile_connect", args=[profile.pk]), fetch_redirect_response=False)

    def test_AC_6_without_wizard_connections_still_return_to_accounts(self):
        response = self.client.get(reverse("social:facebook_callback"), {"error": "access_denied"})
        self.assertRedirects(response, reverse("social:accounts"), fetch_redirect_response=False)

    def test_AC_6_adopt_links_accounts_and_their_instagram(self):
        profile = Profile.objects.create(owner=self.user, name="Loja")
        page = make_account(self.user, None, "1")
        ig = make_account(self.user, None, "ig", "instagram", "IG")
        ig.parent = page
        ig.save()
        request = mock.Mock(user=self.user, session={profiles.ACTIVE_KEY: profile.pk})
        profiles.adopt(request, [page])
        page.refresh_from_db(), ig.refresh_from_db()
        self.assertEqual((page.profile, ig.profile), (profile, profile))

    def test_AC_6_adopt_does_not_move_accounts_of_another_profile(self):
        a, b = (Profile.objects.create(owner=self.user, name=n) for n in "AB")
        account = make_account(self.user, a)
        request = mock.Mock(user=self.user, session={profiles.ACTIVE_KEY: b.pk})
        profiles.adopt(request, [account])
        account.refresh_from_db()
        self.assertEqual(account.profile, a)

    def test_AC_7_done_goes_to_dashboard(self):
        profile = Profile.objects.create(owner=self.user, name="Loja")
        response = self.client.post(reverse("social:profile_done", args=[profile.pk]))
        self.assertRedirects(response, reverse("dashboard:index"))

    def test_AC_8_accounts_page_scoped_to_active_profile(self):
        a, b = (Profile.objects.create(owner=self.user, name=n) for n in "AB")
        make_account(self.user, a, "1", name="Pagina-A")
        make_account(self.user, b, "2", name="Pagina-B")
        self.client.post(reverse("social:profile_enter", args=[a.pk]))
        response = self.client.get(reverse("social:accounts"))
        self.assertContains(response, "Pagina-A")
        self.assertNotContains(response, "Pagina-B")

    def test_AC_8_dashboard_scoped_to_active_profile(self):
        a, b = (Profile.objects.create(owner=self.user, name=n) for n in "AB")
        make_account(self.user, b, "2")
        self.client.post(reverse("social:profile_enter", args=[a.pk]))
        facebook = next(p for p in self.client.get(reverse("dashboard:index")).context["platforms"] if p["name"] == "Facebook")
        self.assertFalse(facebook["connected"])

    def test_AC_8_post_form_destinations_scoped(self):
        a, b = (Profile.objects.create(owner=self.user, name=n) for n in "AB")
        make_account(self.user, a, "1", name="Pagina-A")
        make_account(self.user, b, "2", name="Pagina-B")
        self.client.post(reverse("social:profile_enter", args=[a.pk]))
        response = self.client.get(reverse("social:post_new"))
        self.assertContains(response, "Pagina-A")
        self.assertNotContains(response, "Pagina-B")

    def test_AC_8_without_profiles_everything_is_visible(self):
        make_account(self.user, None, "1", name="Pagina-A")
        self.assertContains(self.client.get(reverse("social:accounts")), "Pagina-A")

    def test_AC_9_dashboard_requires_active_profile(self):
        Profile.objects.create(owner=self.user, name="A")
        self.assertRedirects(self.client.get(reverse("dashboard:index")), reverse("social:profile_select"))

    def test_AC_9_dashboard_open_without_any_profile(self):
        self.assertEqual(self.client.get(reverse("dashboard:index")).status_code, 200)

    def test_AC_10_migration_backfill_creates_principal(self):
        import importlib

        from django.apps import apps as global_apps

        make_account(self.user, None, "1")
        make_account(self.other, None, "2")
        migration = importlib.import_module("apps.social.migrations.0009_profiles")

        class Schema:  # o backfill só usa o registro de apps
            pass

        migration.backfill_principal(global_apps, Schema())
        for user in (self.user, self.other):
            profile = Profile.objects.get(owner=user, name="Principal")
            self.assertEqual(SocialAccount.objects.get(owner=user).profile, profile)

    def test_AC_11_other_users_profile_is_404(self):
        foreign = Profile.objects.create(owner=self.other, name="Dele")
        self.assertEqual(self.client.post(reverse("social:profile_enter", args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("social:profile_connect", args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("social:profile_done", args=[foreign.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("social:profile_select")), "Dele")

    def test_AC_11_stale_active_id_of_another_user_is_ignored(self):
        foreign = Profile.objects.create(owner=self.other, name="Dele")
        session = self.client.session
        session[profiles.ACTIVE_KEY] = foreign.pk
        session.save()
        make_account(self.user, None, "1", name="Minha")
        self.assertContains(self.client.get(reverse("social:accounts")), "Minha")

    def test_AC_12_login_layout(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "data-password-toggle")
        self.assertContains(response, "Entrar")

    def test_AC_12_invalid_credentials_show_error(self):
        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {"username": "alice", "password": "errada"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'role="alert"')

    def test_profile_pages_require_login(self):
        self.client.logout()
        for name in ("social:profile_select", "social:profile_new"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)
