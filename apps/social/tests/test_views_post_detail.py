from pathlib import Path

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.social.models import PublicationTarget
from apps.social.services.meta import MetaApiError

from .publication_helpers import PublicationTestMixin

S = PublicationTarget.Status


class PostDetailTests(PublicationTestMixin, TestCase):
    def detail(self, pub):
        return self.client.get(reverse("social:post_detail", args=[pub.pk]))

    def send(self, pub, **kw):
        return self.client.post(reverse("social:post_send", args=[pub.pk]), follow=kw.get("follow", True))

    # ---- AC-16 -----------------------------------------------------------
    def test_AC_16_detail_shows_content_and_result_per_page(self):
        pub = self.make_publication(text="Texto <b>completo</b>", send=False)
        self.publish.side_effect = [{"photo_id": "p", "post_id": "1_77"}, MetaApiError("x", code=368)]
        self.send(pub)
        response = self.detail(pub)
        self.assertContains(response, "Texto &lt;b&gt;completo&lt;/b&gt;")
        self.assertContains(response, reverse("social:post_image", args=[pub.pk]))
        self.assertContains(response, "https://www.facebook.com/1_77")
        self.assertContains(response, "A Meta bloqueou esta publicação.")
        self.assertContains(response, 'rel="noopener noreferrer"')
        self.assertContains(response, "Tentar novamente")
        self.assertContains(response, "Com falhas")

    def test_AC_16_no_resend_button_when_everything_is_published(self):
        pub = self.make_publication(send=True)
        response = self.detail(pub)
        self.assertNotContains(response, "Tentar novamente")
        self.assertNotContains(response, "Continuar envio")
        self.assertContains(response, "Publicada")

    def test_AC_16_continue_button_when_only_pending_remain(self):
        pub = self.make_publication(self.make_accounts(7))
        with override_settings(PUBLISH_BATCH_SIZE=5):
            self.send(pub)
        response = self.detail(pub)
        self.assertContains(response, "Continuar envio")
        self.assertNotContains(response, "Tentar novamente")

    def test_AC_16_disconnected_failed_target_has_no_resend_button(self):
        accounts = self.make_accounts(1)
        pub = self.make_publication(accounts)
        accounts[0].delete()
        self.send(pub)
        response = self.detail(pub)
        self.assertContains(response, "Conta desconectada.")
        self.assertContains(response, "Página 1")
        self.assertNotContains(response, "Tentar novamente")

    # ---- AC-11 / AC-12 ---------------------------------------------------
    def test_AC_11_send_processes_batches_of_five(self):
        pub = self.make_publication(self.make_accounts(7))
        response = self.send(pub)
        self.assertEqual(self.publish.call_count, 5)
        self.assertContains(response, "2 Página(s) ainda pendente(s)")
        response = self.send(pub)
        self.assertEqual(self.publish.call_count, 7)
        self.assertContains(response, "Publicado em 2 Páginas")

    def test_AC_12_retry_sends_only_failed_ones(self):
        pub = self.make_publication(self.make_accounts(3))
        self.publish.side_effect = [{"photo_id": "p", "post_id": "1_1"}, MetaApiError("x", code=4), {"photo_id": "p", "post_id": "3_3"}]
        self.send(pub)
        self.publish.reset_mock()
        self.publish.side_effect = lambda client, page_id, token, **kw: {"photo_id": "p", "post_id": f"{page_id}_ok"}
        response = self.send(pub)
        self.assertEqual([c.args[1] for c in self.publish.call_args_list], ["2"])
        self.assertContains(response, "Publicado em 1 Página")

    def test_AC_12_send_with_nothing_to_do_informs_and_does_not_call_meta(self):
        pub = self.make_publication(send=True)
        self.publish.reset_mock()
        response = self.send(pub)
        self.publish.assert_not_called()
        self.assertContains(response, "Nada a enviar")

    @override_settings(META_APP_SECRET="")
    def test_send_when_not_configured_does_not_call_meta(self):
        pub = self.make_publication()
        response = self.send(pub)
        self.assertContains(response, "Integração com a Meta não configurada")
        self.publish.assert_not_called()

    # ---- AC-17 -----------------------------------------------------------
    def test_AC_17_owner_gets_the_image_with_safe_headers(self):
        pub = self.make_publication()
        response = self.client.get(reverse("social:post_image", args=[pub.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("private", response["Cache-Control"])
        self.assertEqual(b"".join(response.streaming_content)[:2], b"\xff\xd8")

    def test_AC_17_missing_file_is_404(self):
        pub = self.make_publication()
        (Path(self.media) / pub.image.name).unlink()
        self.assertEqual(self.client.get(reverse("social:post_image", args=[pub.pk])).status_code, 404)

    def test_AC_17_there_is_no_public_media_url(self):
        pub = self.make_publication()
        self.assertEqual(self.client.get(f"/media/{pub.image.name}").status_code, 404)

    # ---- AC-18 -----------------------------------------------------------
    def test_AC_18_other_users_get_404_everywhere_and_nothing_is_sent(self):
        pub = self.make_publication()
        self.client.force_login(self.bob)
        for name, method in (("social:post_detail", "get"), ("social:post_send", "post"), ("social:post_image", "get")):
            with self.subTest(name):
                response = getattr(self.client, method)(reverse(name, args=[pub.pk]))
                self.assertEqual(response.status_code, 404)
        self.publish.assert_not_called()
        self.assertEqual({t.status for t in pub.targets.all()}, {S.PENDING})

    # ---- AC-20 -----------------------------------------------------------
    def test_AC_20_send_rejects_get_and_requires_csrf(self):
        pub = self.make_publication()
        self.assertEqual(self.client.get(reverse("social:post_send", args=[pub.pk])).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.alice)
        self.assertEqual(strict.post(reverse("social:post_send", args=[pub.pk])).status_code, 403)
        self.publish.assert_not_called()

    def test_AC_20_anonymous_is_sent_to_login(self):
        pub = self.make_publication()
        self.client.logout()
        for name, method in (("social:post_detail", "get"), ("social:post_send", "post"), ("social:post_image", "get")):
            with self.subTest(name):
                url = reverse(name, args=[pub.pk])
                response = getattr(self.client, method)(url)
                self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}", fetch_redirect_response=False)
        self.publish.assert_not_called()
