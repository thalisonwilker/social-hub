from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.images import sanitize_image
from apps.social.models import Publication, PublicationTarget
from apps.social.services import publishing
from apps.social.services.meta import MetaApiError

from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_threads_publisher import PERMALINK, TEXT, threads_mocks
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status


@override_settings(**THREADS_SETTINGS)
class MixedWithImageTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.pages = self.make_accounts(2)
        self.threads = make_threads_account(self.alice, "900")
        self.pub = publishing.create_publication(self.alice, TEXT, sanitize_image(make_upload()), [*self.pages, self.threads])

    def test_AC_19_each_platform_publishes_the_image_with_its_own_flow(self):
        """AC-19: Facebook foto + texto como na 0003; Threads imagem + texto; resultado por alvo."""
        with threads_mocks() as api:
            result = publishing.send_pending(self.pub)
        self.assertEqual((result.attempted, result.published, result.failed), (3, 3, 0))
        self.assertEqual(self.publish.call_count, 2)
        for call in self.publish.call_args_list:
            self.assertEqual(call.kwargs["message"], TEXT)
            self.assertEqual(call.kwargs["content_type"], "image/jpeg")
        api["create_image_container"].assert_called_once()
        api["create_text_container"].assert_not_called()
        self.assertEqual(self.pub.status, Publication.Status.PUBLISHED)
        self.assertEqual(self.pub.targets.get(platform="threads").permalink, PERMALINK)

    def test_AC_19_threads_image_failure_does_not_affect_facebook_targets(self):
        """AC-19: erro do Threads com imagem → alvos do Facebook publicados e o do Threads failed."""
        with threads_mocks(statuses=("ERROR",)):
            result = publishing.send_pending(self.pub)
        self.assertEqual((result.published, result.failed), (2, 1))
        self.assertEqual(self.pub.targets.filter(platform="facebook_page", status=S.PUBLISHED).count(), 2)
        threads_target = self.pub.targets.get(platform="threads")
        self.assertEqual((threads_target.status, threads_target.error_message), (S.FAILED, publishing.MSG_THREADS_IMAGE_REJECTED))

    def test_AC_19_facebook_error_does_not_affect_the_threads_image_target(self):
        """AC-19: erro numa Página não impede o Threads de publicar a imagem."""
        self.publish.side_effect = MetaApiError("x", code=368)
        with threads_mocks():
            result = publishing.send_pending(self.pub)
        self.assertEqual((result.published, result.failed), (1, 2))
        self.assertEqual(self.pub.targets.get(platform="threads").status, S.PUBLISHED)

    def test_AC_19_retry_only_resends_the_failed_threads_target_with_a_new_url(self):
        """AC-19: tentar de novo reenvia só o alvo falho; Facebook não é reenviado; nova URL assinada."""
        with threads_mocks(statuses=("ERROR",)) as first:
            publishing.send_pending(self.pub)
        first_url = first["create_image_container"].call_args.args[3]
        self.publish.reset_mock()
        with threads_mocks(create_image_container={"return_value": "c-img-2"}) as second:
            result = publishing.send_pending(self.pub)
        self.assertEqual((result.attempted, result.published), (1, 1))
        self.publish.assert_not_called()
        second["create_image_container"].assert_called_once()
        self.assertTrue(second["create_image_container"].call_args.args[3].startswith(first_url.split("?")[0]))

    def test_AC_19_form_to_detail_end_to_end(self):
        """AC-19: pelo formulário, Facebook + Threads com imagem publicam e o detalhe mostra os dois links."""
        with threads_mocks() as api:
            response = self.client.post(
                reverse("social:post_new"),
                {"text": "Promo", "accounts": [self.pages[0].pk, self.threads.pk], "image": make_upload()},
                follow=True,
            )
        self.assertContains(response, PERMALINK)
        self.assertContains(response, f"https://www.facebook.com/{self.pages[0].external_id}_77")
        api["create_image_container"].assert_called_once()


class SpecSupersessionTests(TestCase):
    def test_AC_21_older_specs_point_to_the_0005_supersession(self):
        """AC-21: a spec 0004 (AC-14, AC-17, AC-21, non-goal) e a 0003 apontam para a 0005; sem a regra antiga de 'imagem ignorada'."""
        from pathlib import Path

        root = Path(__file__).resolve().parents[3] / "specs"
        spec4 = (root / "0004-threads-conectar-e-publicar/spec.md").read_text()
        for heading in ("### AC-14", "### AC-17", "### AC-21"):
            block = spec4.split(heading, 1)[1].split("\n### ", 1)[0]
            self.assertIn("0005", block, heading)
        self.assertNotIn("**nenhuma imagem é enviada**", spec4)
        self.assertIn("0005", spec4.split("## Fora de escopo", 1)[1])
        self.assertIn("0005", (root / "0003-publicar-no-facebook/spec.md").read_text())
