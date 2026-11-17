import logging
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase, override_settings

from apps.social import public
from apps.social.images import sanitize_image
from apps.social.models import Publication, PublicationTarget
from apps.social.services import publishing, threads_publish
from apps.social.services.meta import MetaApiError
from apps.social.services.threads import ThreadsClient

from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_threads_publisher import PERMALINK, TEXT, Clock, threads_mocks
from .threads_helpers import HOST, THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status
SETTINGS = {**THREADS_SETTINGS, "THREADS_IMAGE_WAIT_SECONDS": 60, "PUBLIC_BASE_URL": ""}


@override_settings(**SETTINGS)
class ImagePublisherTests(PublicationTestMixin, TestCase):
    """Publicador isolado (cliente falso, relógio controlado)."""

    def setUp(self):
        super().setUp()
        self.account = make_threads_account(self.alice)
        self.publication = publishing.create_publication(self.alice, TEXT, sanitize_image(make_upload()), [self.account])
        self.target = self.publication.targets.select_related("account").get()
        self.client_mock = mock.create_autospec(ThreadsClient, instance=True)
        self.client_mock.create_image_container.return_value = "ci-1"
        self.client_mock.publish_container.return_value = "m-1"
        self.client_mock.get_permalink.return_value = PERMALINK
        self.clock = Clock()
        self.url_calls = 0

    def factory(self):
        self.url_calls += 1
        return public.build_public_image_url(self.publication)

    def run_publish(self, statuses, **kw):
        queue = list(statuses)
        error = kw.pop("error", "")
        self.client_mock.container_status.side_effect = lambda c, t: {
            "status": queue.pop(0) if len(queue) > 1 else queue[0], "error_message": error}
        return threads_publish.publish_image(
            self.target, self.client_mock, "tok", TEXT, self.factory, sleep=self.clock.sleep, clock=self.clock, **kw)

    def test_AC_11_creates_image_container_with_signed_url_and_remembers_the_id_before_waiting(self):
        """AC-11: container IMAGE criado com a URL assinada; id gravado no alvo ANTES da consulta de status."""
        seen = {}

        def status(container_id, token):
            self.target.refresh_from_db()
            seen["id"] = self.target.external_container_id
            return {"status": "FINISHED", "error_message": ""}

        self.client_mock.container_status.side_effect = status
        threads_publish.publish_image(self.target, self.client_mock, "tok", TEXT, self.factory, sleep=self.clock.sleep, clock=self.clock)
        self.assertEqual(seen["id"], "ci-1")
        (user, token, text, url), _ = self.client_mock.create_image_container.call_args
        self.assertEqual((user, token, text), (self.account.external_id, "tok", TEXT))
        self.assertTrue(url.startswith(f"https://{HOST}/publico/imagem.jpg?t="))
        self.client_mock.create_text_container.assert_not_called()

    def test_AC_12_finished_publishes_and_reads_the_permalink(self):
        """AC-12: IN_PROGRESS → FINISHED (consulta a cada 3 s) → publica e lê o permalink."""
        outcome = self.run_publish(["IN_PROGRESS", "IN_PROGRESS", "FINISHED"])
        self.assertEqual((outcome.post_id, outcome.permalink), ("m-1", PERMALINK))
        self.assertEqual(self.clock.t, 6.0)  # 2 esperas de 3 s
        self.client_mock.publish_container.assert_called_once_with(self.account.external_id, "tok", "ci-1")

    def test_AC_12_already_published_container_is_not_republished(self):
        """AC-12: PUBLISHED na consulta → sem republicar."""
        outcome = self.run_publish(["PUBLISHED"])
        self.assertEqual((outcome.post_id, outcome.permalink), ("", ""))
        self.client_mock.publish_container.assert_not_called()

    def test_AC_13_error_and_expired_raise_and_log_only_the_enum(self):
        """AC-13: ERROR/EXPIRED → ContainerFailed; o enum da Meta vai ao log (saneado), sem URL nem texto."""
        for status in ("ERROR", "EXPIRED"):
            with self.subTest(status=status), self.assertLogs("apps.social.meta", level="WARNING") as logs:
                with self.assertRaises(threads_publish.ContainerFailed) as ctx:
                    self.run_publish([status], error="FAILED_DOWNLOADING_IMAGE <script>")
                self.assertEqual(ctx.exception.status, status)
                out = "\n".join(logs.output)
                self.assertIn("threads_container_error", out)
                self.assertIn("code=FAILED_DOWNLOADING_IMAGEscript", out)
                for secret in (TEXT, "https://", "?t="):
                    self.assertNotIn(secret, out)
            self.client_mock.create_image_container.reset_mock()

    def test_AC_14_wait_limit_raises_not_ready_and_keeps_the_container(self):
        """AC-14: IN_PROGRESS além de THREADS_IMAGE_WAIT_SECONDS → ContainerNotReady; id mantido; nada publicado."""
        with self.assertRaises(threads_publish.ContainerNotReady):
            self.run_publish(["IN_PROGRESS"])
        self.assertGreaterEqual(self.clock.t, 60)
        self.target.refresh_from_db()
        self.assertEqual(self.target.external_container_id, "ci-1")
        self.client_mock.publish_container.assert_not_called()
        self.client_mock.create_text_container.assert_not_called()

    def test_AC_15_existing_container_is_reused_without_a_new_url(self):
        """AC-15: com external_container_id gravado não cria container nem gera URL."""
        self.target.external_container_id = "ci-0"
        outcome = self.run_publish(["FINISHED"])
        self.assertEqual(outcome.post_id, "m-1")
        self.client_mock.create_image_container.assert_not_called()
        self.assertEqual(self.url_calls, 0)
        self.client_mock.publish_container.assert_called_once_with(self.account.external_id, "tok", "ci-0")

    def test_AC_18_wait_is_limited_by_max_wait(self):
        """AC-18: max_wait menor que a configuração limita a espera."""
        with self.assertRaises(threads_publish.ContainerNotReady):
            self.run_publish(["IN_PROGRESS"], max_wait=10)
        self.assertGreaterEqual(self.clock.t, 10)
        self.assertLess(self.clock.t, 20)


@override_settings(**SETTINGS)
class ImageDispatchTests(PublicationTestMixin, TestCase):
    """Fluxo completo por `send_pending` com a Threads API mockada."""

    def setUp(self):
        super().setUp()
        self.threads = make_threads_account(self.alice, "900")

    def pub(self, image=True):
        return publishing.create_publication(self.alice, TEXT, sanitize_image(make_upload()) if image else None, [self.threads])

    def target(self, pub):
        return pub.targets.get()

    def test_AC_12_image_publication_publishes_image_and_text(self):
        """AC-12: publicação com imagem → container IMAGE, `published` com id e link."""
        pub = self.pub()
        with threads_mocks() as api:
            result = publishing.send_pending(pub)
        self.assertEqual((result.published, result.failed), (1, 0))
        api["create_image_container"].assert_called_once()
        api["create_text_container"].assert_not_called()
        t = self.target(pub)
        self.assertEqual((t.status, t.external_post_id, t.permalink), (S.PUBLISHED, "m-1", PERMALINK))

    def test_AC_16_without_image_the_container_is_text(self):
        """AC-16: sem imagem → container TEXT como na 0004; nenhuma URL pública é envolvida."""
        pub = self.pub(image=False)
        with threads_mocks() as api, mock.patch("apps.social.public.build_public_image_url") as build:
            publishing.send_pending(pub)
        api["create_text_container"].assert_called_once_with("900", "threads-long-token", TEXT)
        api["create_image_container"].assert_not_called()
        build.assert_not_called()
        self.assertEqual(self.target(pub).status, S.PUBLISHED)

    def test_AC_13_error_fails_discards_the_container_and_never_publishes_text(self):
        """AC-13: ERROR → failed com a mensagem da imagem; id descartado; nada publicado; reenvio gera container e URL novos."""
        pub = self.pub()
        with threads_mocks(statuses=("ERROR",)) as api:
            publishing.send_pending(pub)
        t = self.target(pub)
        self.assertEqual((t.status, t.error_message), (S.FAILED, publishing.MSG_THREADS_IMAGE_REJECTED))
        self.assertEqual(t.external_container_id, "")
        api["publish_container"].assert_not_called()
        api["create_text_container"].assert_not_called()
        first_url = api["create_image_container"].call_args.args[3]
        with threads_mocks(create_image_container={"return_value": "c-img-2"}) as api2:
            publishing.send_pending(pub)
        self.assertEqual(self.target(pub).status, S.PUBLISHED)
        api2["create_image_container"].assert_called_once()
        self.assertNotEqual(api2["create_image_container"].call_args.args[3], "")
        self.assertIn("/publico/imagem.jpg?t=", first_url)

    def test_AC_13_expired_uses_the_same_image_message(self):
        """AC-13: EXPIRED com imagem → mesma mensagem amigável, id descartado."""
        pub = self.pub()
        with threads_mocks(statuses=("EXPIRED",)):
            publishing.send_pending(pub)
        t = self.target(pub)
        self.assertEqual(t.error_message, publishing.MSG_THREADS_IMAGE_REJECTED)
        self.assertEqual(t.external_container_id, "")

    def test_AC_14_wait_exhausted_fails_keeps_container_and_does_not_post_text(self):
        """AC-14: espera esgotada → failed reenviável, id mantido, nenhum post de só texto; retomada reutiliza (AC-15)."""
        pub = self.pub()
        clock = Clock()
        fake_time = SimpleNamespace(sleep=clock.sleep, monotonic=clock)
        with threads_mocks(statuses=("IN_PROGRESS",)) as api, mock.patch.object(threads_publish, "time", fake_time):
            publishing.send_pending(pub)
        t = self.target(pub)
        self.assertEqual((t.status, t.error_message), (S.FAILED, publishing.MSG_THREADS_IMAGE_PENDING))
        self.assertEqual(t.external_container_id, "c-img-1")
        api["publish_container"].assert_not_called()
        api["create_text_container"].assert_not_called()
        with threads_mocks() as api2:
            publishing.send_pending(pub)  # AC-15
        api2["create_image_container"].assert_not_called()
        api2["publish_container"].assert_called_once_with("900", "threads-long-token", "c-img-1")
        self.assertEqual(self.target(pub).status, S.PUBLISHED)

    def test_AC_11_without_public_address_the_target_fails_without_calling_the_meta(self):
        """AC-11: sem endereço público (config mudou depois de criar) o alvo falha com mensagem clara."""
        pub = self.pub()
        with override_settings(THREADS_REDIRECT_URI="http://localhost/cb/"), threads_mocks() as api:
            publishing.send_pending(pub)
        t = self.target(pub)
        self.assertEqual((t.status, t.error_message), (S.FAILED, publishing.MSG_THREADS_NO_PUBLIC_URL))
        api["create_image_container"].assert_not_called()

    def test_AC_11_missing_image_file_fails_without_calling_the_meta(self):
        """AC-11: arquivo da imagem sumiu do volume → falha amigável, sem chamar a Meta."""
        pub = self.pub()
        pub.image.delete(save=False)
        with threads_mocks() as api:
            publishing.send_pending(pub)
        t = self.target(pub)
        self.assertEqual((t.status, t.error_message), (S.FAILED, publishing.MSG_IMAGE_MISSING))
        api["create_image_container"].assert_not_called()

    def test_AC_11_meta_errors_on_the_image_container_use_the_usual_messages(self):
        """AC-11: erro da Meta ao criar o container de imagem → mensagem amigável (0004 AC-20), sem texto cru."""
        pub = self.pub()
        with threads_mocks(create_image_container={"side_effect": MetaApiError(f"{TEXT} segredo", code=4)}):
            publishing.send_pending(pub)
        t = self.target(pub)
        self.assertEqual(t.error_message, publishing.MSG_RATE_LIMIT)
        self.assertNotIn("segredo", t.error_message)

    def test_AC_11_signed_url_never_reaches_logs_or_target_fields(self):
        """AC-11: a URL assinada não aparece em logs, mensagens nem campos do alvo."""
        pub = self.pub()
        with self.assertLogs("apps.social", level=logging.INFO) as logs, threads_mocks() as api:
            publishing.send_pending(pub)
        url = api["create_image_container"].call_args.args[3]
        token = url.split("t=", 1)[1]
        self.assertNotIn(token, "\n".join(logs.output))
        t = self.target(pub)
        self.assertNotIn(token, f"{t.error_message}{t.external_container_id}{t.permalink}")
