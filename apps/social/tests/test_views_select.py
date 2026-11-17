from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import SocialAccount

from .helpers import PAGE_TOKEN_1, VALID_META_SETTINGS, graph_patches

SELECT = "social:facebook_select"


@override_settings(**VALID_META_SETTINGS)
class SelectViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice", password="x")

    def setUp(self):
        self.client.force_login(self.user)

    def prepare_pending(self):
        self.client.post(reverse("social:facebook_connect"))
        state = self.client.session["fb_oauth_state"]["value"]
        with graph_patches():
            self.client.get(reverse("social:facebook_callback"), {"code": "abc", "state": state})

    def test_AC_3_selection_page_lists_pages_with_checkboxes_and_select_all(self):
        self.prepare_pending()
        response = self.client.get(reverse(SELECT))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="pages"', count=2)
        self.assertContains(response, "Marcar todas")
        self.assertContains(response, "Café ☕")
        self.assertNotContains(response, "<b>Central</b>")  # escapado
        self.assertContains(response, "&lt;b&gt;Central&lt;/b&gt;")
        self.assertNotContains(response, PAGE_TOKEN_1)

    def test_AC_4_post_connects_selected_pages(self):
        self.prepare_pending()
        response = self.client.post(reverse(SELECT), {"pages": ["1", "2"]}, follow=True)
        self.assertRedirects(response, reverse("social:accounts"))
        self.assertContains(response, "2 Páginas conectadas")
        self.assertEqual(SocialAccount.objects.filter(owner=self.user).count(), 2)
        self.assertEqual(self.client.get(reverse(SELECT)).status_code, 302)  # sessão limpa

    def test_AC_4_single_page_message(self):
        self.prepare_pending()
        response = self.client.post(reverse(SELECT), {"pages": ["1"]}, follow=True)
        self.assertContains(response, "1 Página conectada")

    def test_AC_5_page_already_connected_is_flagged_and_updated(self):
        old = SocialAccount(owner=self.user, platform="facebook_page", external_id="1", name="Antigo")
        old.set_token("velho")
        old.save()
        self.prepare_pending()
        self.assertContains(self.client.get(reverse(SELECT)), "Já conectada")
        self.client.post(reverse(SELECT), {"pages": ["1"]})
        self.assertEqual(SocialAccount.objects.count(), 1)
        self.assertEqual(SocialAccount.objects.get().get_token(), PAGE_TOKEN_1)

    def test_AC_10_empty_selection_redisplays_with_error(self):
        self.prepare_pending()
        response = self.client.post(reverse(SELECT), {})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Marque ao menos uma Página")
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_AC_10_unknown_page_id_is_rejected(self):
        self.prepare_pending()
        response = self.client.post(reverse(SELECT), {"pages": ["1", "999"]})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Seleção inválida", status_code=400)
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_AC_10_expired_selection_returns_to_accounts_with_message(self):
        for method in ("get", "post"):
            with self.subTest(method):
                response = getattr(self.client, method)(reverse(SELECT), follow=True)
                self.assertRedirects(response, reverse("social:accounts"))
                self.assertContains(response, "A seleção expirou")
