import os
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.social import public
from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services.meta import GraphClient, MetaApiError
from apps.social.services.threads import ThreadsClient

from .evolution_helpers import EVOLUTION_SETTINGS, make_whatsapp_account
from .publication_helpers import PublicationTestMixin
from .test_instagram_model import make_instagram, make_page
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status


@override_settings(**{**THREADS_SETTINGS, **EVOLUTION_SETTINGS})
class DeletionViewsTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.fb = self.make_accounts(1)[0]
        self.th = make_threads_account(self.alice, "900")
        self.ig = make_instagram(self.alice, make_page(self.alice, "50"))
        self.wa = make_whatsapp_account(self.alice, "loja", key="k")
        self.pub = self.make_publication([self.fb, self.th, self.ig, self.wa])
        self.pub.targets.update(status=S.PUBLISHED, external_post_id="PID", permalink="https://x/p")
        self.other = Client()
        self.other.force_login(self.bob)

    def t(self, platform):
        return self.pub.targets.get(platform=platform)

    def url(self, name, *args):
        return reverse(f"social:{name}", args=args)

    # ---- AC-5 / AC-6 ---------------------------------------------------------
    def test_AC_5_delete_facebook_target_via_view(self):
        with mock.patch.object(GraphClient, "delete_post", return_value=True) as delete_post:
            response = self.client.post(self.url("target_delete_remote", self.pub.pk, self.t("facebook_page").pk), follow=True)
        delete_post.assert_called_once_with("PID", "token-1")
        self.assertContains(response, "Post apagado na plataforma.")
        self.assertTrue(self.t("facebook_page").is_deleted)
        self.assertEqual(Publication.objects.count(), 1)  # o registro continua

    def test_AC_6_delete_threads_target_via_view(self):
        with mock.patch.object(ThreadsClient, "delete_media", return_value=True) as delete_media:
            self.client.post(self.url("target_delete_remote", self.pub.pk, self.t("threads").pk))
        self.assertEqual(delete_media.call_args.args[0], "PID")
        self.assertTrue(self.t("threads").is_deleted)

    def test_AC_7_unsupported_platforms_are_refused_without_calling_anything(self):
        with mock.patch.object(GraphClient, "delete_post") as g, mock.patch.object(ThreadsClient, "delete_media") as t:
            for platform in ("instagram", "whatsapp_status"):
                response = self.client.post(self.url("target_delete_remote", self.pub.pk, self.t(platform).pk), follow=True)
                self.assertContains(response, "Apague pelo app")
                self.assertFalse(self.t(platform).is_deleted)
        g.assert_not_called()
        t.assert_not_called()

    def test_AC_9_failure_keeps_everything_and_shows_a_friendly_message(self):
        with mock.patch.object(GraphClient, "delete_post", side_effect=MetaApiError("RAW-SECRETO", code=10, status=400)):
            response = self.client.post(self.url("target_delete_remote", self.pub.pk, self.t("facebook_page").pk), follow=True)
        self.assertContains(response, "Sem permissão para apagar este post.")
        self.assertNotContains(response, "RAW-SECRETO")
        self.assertFalse(self.t("facebook_page").is_deleted)

    def test_AC_10_unknown_outcome_message(self):
        with mock.patch.object(GraphClient, "delete_post", side_effect=MetaApiError("x", code="timeout", outcome_unknown=True)):
            response = self.client.post(self.url("target_delete_remote", self.pub.pk, self.t("facebook_page").pk), follow=True)
        self.assertContains(response, "Não foi possível confirmar a exclusão")
        self.assertFalse(self.t("facebook_page").is_deleted)

    def test_AC_12_delete_whole_publication_on_platform_summarizes(self):
        with mock.patch.object(GraphClient, "delete_post", return_value=True), mock.patch.object(
            ThreadsClient, "delete_media", side_effect=MetaApiError("x", code=4, status=400)
        ):
            response = self.client.post(self.url("post_delete_remote", self.pub.pk), follow=True)
        self.assertContains(response, "1 apagado(s), 1 com falha e 2 sem exclusão pelo Hub.")
        self.assertEqual(Publication.objects.count(), 1)

    # ---- AC-1 / AC-2 / AC-3 ----------------------------------------------------------
    def test_AC_1_remove_publication_redirects_to_the_list_and_deletes_the_file(self):
        path = self.pub.image.path
        with mock.patch.object(GraphClient, "delete_post") as g:
            response = self.client.post(self.url("post_remove", self.pub.pk), follow=True)
        g.assert_not_called()
        self.assertRedirects(response, reverse("social:posts"))
        self.assertContains(response, "Publicação removida do Hub.")
        self.assertEqual(Publication.objects.count(), 0)
        self.assertFalse(os.path.exists(path))

    def test_AC_2_sending_blocks_removal_with_a_message(self):
        self.pub.targets.filter(platform="threads").update(status=S.SENDING)
        response = self.client.post(self.url("post_remove", self.pub.pk), follow=True)
        self.assertContains(response, "Há envio em andamento")
        self.assertEqual(Publication.objects.count(), 1)

    def test_AC_3_remove_one_target_then_the_last_removes_the_publication(self):
        for platform in ("instagram", "whatsapp_status", "threads"):
            response = self.client.post(self.url("target_remove", self.pub.pk, self.t(platform).pk), follow=True)
            self.assertContains(response, "Destino removido do Hub.")
        self.assertEqual(self.pub.targets.count(), 1)
        response = self.client.post(self.url("target_remove", self.pub.pk, self.t("facebook_page").pk), follow=True)
        self.assertRedirects(response, reverse("social:posts"))
        self.assertEqual(Publication.objects.count(), 0)

    # ---- AC-15 ------------------------------------------------------------------------
    def test_AC_15_only_post_and_only_the_owner(self):
        urls = [
            self.url("post_remove", self.pub.pk),
            self.url("post_delete_remote", self.pub.pk),
            self.url("target_remove", self.pub.pk, self.t("facebook_page").pk),
            self.url("target_delete_remote", self.pub.pk, self.t("facebook_page").pk),
        ]
        with mock.patch.object(GraphClient, "delete_post") as g, mock.patch.object(ThreadsClient, "delete_media") as t:
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 405, url)
                self.assertEqual(self.other.post(url).status_code, 404, url)
        g.assert_not_called()
        t.assert_not_called()
        self.assertEqual((Publication.objects.count(), PublicationTarget.objects.count()), (1, 4))

    def test_AC_15_csrf_is_enforced(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.alice)
        self.assertEqual(strict.post(self.url("post_remove", self.pub.pk)).status_code, 403)
        self.assertEqual(Publication.objects.count(), 1)

    def test_AC_16_public_image_url_is_404_after_removal(self):
        self.pub.targets.update(status=S.PENDING)  # em andamento: a URL valia
        token = public.sign_image_token(self.pub.pk)
        anon = Client()
        self.assertEqual(anon.get(f"/publico/imagem.jpg?t={token}").status_code, 200)
        self.client.post(self.url("post_remove", self.pub.pk))
        self.assertEqual(anon.get(f"/publico/imagem.jpg?t={token}").status_code, 404)
        self.assertEqual(anon.get(f"/publico/instagram.jpg?t={token}").status_code, 404)
