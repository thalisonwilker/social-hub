from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import SocialAccount
from apps.social.services.meta import MetaApiError

from .helpers import VALID_META_SETTINGS, graph_patches

CONNECT = "social:facebook_connect"
CALLBACK = "social:facebook_callback"


@override_settings(**VALID_META_SETTINGS)
class OAuthViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice", password="x")

    def setUp(self):
        self.client.force_login(self.user)

    def start(self):
        response = self.client.post(reverse(CONNECT))
        return parse_qs(urlparse(response["Location"]).query)["state"][0]

    def callback(self, **params):
        return self.client.get(reverse(CALLBACK), params, follow=True)

    # ---- AC-1 / AC-2 -----------------------------------------------------
    @override_settings(META_APP_ID="")
    def test_AC_1_connect_when_not_configured_does_not_start_oauth(self):
        response = self.client.post(reverse(CONNECT), follow=True)
        self.assertRedirects(response, reverse("social:accounts"))
        self.assertContains(response, "Integração com a Meta não configurada")

    def test_AC_2_connect_redirects_to_meta_dialog_with_state(self):
        response = self.client.post(reverse(CONNECT))
        self.assertEqual(response.status_code, 302)
        url = urlparse(response["Location"])
        self.assertEqual(f"{url.scheme}://{url.netloc}{url.path}", "https://www.facebook.com/v27.0/dialog/oauth")
        query = parse_qs(url.query)
        self.assertEqual(query["client_id"], ["123"])
        self.assertEqual(query["config_id"], ["456"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["override_default_response_type"], ["true"])
        self.assertEqual(query["redirect_uri"], [VALID_META_SETTINGS["META_REDIRECT_URI"]])
        self.assertEqual(query["state"][0], self.client.session["fb_oauth_state"]["value"])

    def test_AC_2_connect_rejects_get(self):
        self.assertEqual(self.client.get(reverse(CONNECT)).status_code, 405)

    # ---- AC-3 ------------------------------------------------------------
    def test_AC_3_valid_callback_goes_to_selection_without_creating_accounts(self):
        state = self.start()
        with graph_patches():
            response = self.callback(code="abc", state=state)
        self.assertRedirects(response, reverse("social:facebook_select"))
        self.assertEqual(SocialAccount.objects.count(), 0)
        self.assertContains(response, "Marcar todas")

    # ---- AC-6 ------------------------------------------------------------
    def test_AC_6_user_denies_authorization(self):
        self.start()
        with graph_patches() as mocks:
            response = self.callback(error="access_denied", error_reason="user_denied")
        self.assertRedirects(response, reverse("social:accounts"))
        self.assertContains(response, "Autorização cancelada")
        for m in mocks:
            m.assert_not_called()
        self.assertEqual(SocialAccount.objects.count(), 0)

    # ---- AC-7 ------------------------------------------------------------
    def test_AC_7_invalid_missing_or_reused_state_is_rejected(self):
        state = self.start()
        cases = {"errado": {"code": "abc", "state": "errado"}, "ausente": {"code": "abc"}}
        for name, params in cases.items():
            with self.subTest(name):
                self.start()
                with graph_patches() as mocks, self.assertLogs("apps.social.meta", "WARNING") as logs:
                    response = self.callback(**params)
                self.assertContains(response, "Não foi possível validar a conexão")
                self.assertIn("oauth_state_rejected", "\n".join(logs.output))
                for m in mocks:
                    m.assert_not_called()
        # reuso: o primeiro uso consome o state
        state = self.start()
        with graph_patches():
            self.callback(code="abc", state=state)
        with graph_patches() as mocks:
            response = self.callback(code="abc", state=state)
        self.assertContains(response, "Não foi possível validar a conexão")
        for m in mocks:
            m.assert_not_called()
        self.assertEqual(SocialAccount.objects.count(), 0)

    # ---- AC-8 ------------------------------------------------------------
    def test_AC_8_meta_failure_shows_generic_message_and_creates_nothing(self):
        state = self.start()
        with graph_patches(error=MetaApiError("x", code=100)):
            response = self.callback(code="abc", state=state)
        self.assertRedirects(response, reverse("social:accounts"))
        self.assertContains(response, "Não foi possível concluir a conexão com a Meta")
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_AC_8_missing_code_with_valid_state(self):
        state = self.start()
        response = self.callback(state=state)
        self.assertContains(response, "Não foi possível concluir a conexão com a Meta")

    # ---- AC-9 ------------------------------------------------------------
    def test_AC_9_no_pages_found(self):
        state = self.start()
        with graph_patches(pages=[]):
            response = self.callback(code="abc", state=state)
        self.assertRedirects(response, reverse("social:accounts"))
        self.assertContains(response, "Nenhuma Página encontrada")
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_edge_pages_without_permission_get_specific_message(self):
        state = self.start()
        sem_token = [{"id": "1", "name": "X", "category": "", "picture_url": "", "access_token": None, "tasks": []}]
        with graph_patches(pages=sem_token):
            response = self.callback(code="abc", state=state)
        self.assertContains(response, "não tem permissão para gerenciá-las")


@override_settings(**VALID_META_SETTINGS)
class OAuthAuthTests(TestCase):
    def test_AC_17_anonymous_users_are_sent_to_login(self):
        for name, method in ((CONNECT, "post"), (CALLBACK, "get"), ("social:facebook_select", "get")):
            with self.subTest(name):
                response = getattr(self.client, method)(reverse(name))
                self.assertRedirects(
                    response, f"{reverse('accounts:login')}?next={reverse(name)}", fetch_redirect_response=False
                )
