import logging
from unittest import mock

from django.test import TestCase, override_settings

from apps.social import public
from apps.social.images import sanitize_image
from apps.social.models import PublicationTarget, SocialAccount
from apps.social.services import instagram_publish, publishing
from apps.social.services.meta import GraphClient, MetaApiError
from apps.social.tests.test_threads_publisher import Clock

from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_instagram_model import make_instagram, make_page
from .threads_helpers import HOST, THREADS_SETTINGS

S = PublicationTarget.Status
CAPTION = "Legenda confidencial #ig"
PERMALINK = "https://www.instagram.com/p/ABC/"
SETTINGS = {**THREADS_SETTINGS, "INSTAGRAM_CONTAINER_WAIT_SECONDS": 60, "PUBLIC_BASE_URL": ""}


def graph_mock(statuses=("FINISHED",)):
    client = mock.create_autospec(GraphClient, instance=True)
    client.create_instagram_container.return_value = "c-1"
    client.publish_instagram_container.return_value = "m-1"
    client.get_instagram_permalink.return_value = PERMALINK
    queue = list(statuses)
    client.instagram_container_status.side_effect = lambda c, t: {"status": queue.pop(0) if len(queue) > 1 else queue[0]}
    return client


@override_settings(**SETTINGS)
class InstagramPublisherTests(PublicationTestMixin, TestCase):
    """Publicador isolado (cliente falso, relógio controlado)."""

    def setUp(self):
        super().setUp()
        self.page = make_page(self.alice, "50")
        self.ig = make_instagram(self.alice, self.page)
        self.publication = publishing.create_publication(self.alice, CAPTION, sanitize_image(make_upload()), [self.ig])
        self.target = self.publication.targets.select_related("account").get()
        self.clock = Clock()
        self.urls = 0

    def factory(self):
        self.urls += 1
        return public.build_instagram_image_url(self.publication)

    def run_publish(self, client, **kw):
        return instagram_publish.publish_image(
            self.target, client, "tok", CAPTION, self.factory, sleep=self.clock.sleep, clock=self.clock, **kw
        )

    def test_AC_13_container_has_signed_jpeg_url_and_is_remembered_before_waiting(self):
        client, seen = graph_mock(), {}

        def status(container_id, token):
            self.target.refresh_from_db()
            seen["id"] = self.target.external_container_id
            return {"status": "FINISHED"}

        client.instagram_container_status.side_effect = status
        with self.assertLogs("apps.social.meta", level="INFO") as logs:
            self.run_publish(client)
        self.assertEqual(seen["id"], "c-1")
        ig_id, token, url, caption = client.create_instagram_container.call_args.args
        self.assertEqual((ig_id, token, caption), (self.ig.external_id, "tok", CAPTION))
        self.assertTrue(url.startswith(f"https://{HOST}/publico/instagram.jpg?t="))
        self.assertIn("instagram_container_created", "\n".join(logs.output))

    def test_AC_14_finished_publishes_and_reads_the_permalink(self):
        client = graph_mock(["IN_PROGRESS", "IN_PROGRESS", "FINISHED"])
        outcome = self.run_publish(client)
        self.assertEqual((outcome.post_id, outcome.permalink), ("m-1", PERMALINK))
        self.assertEqual(self.clock.t, 6.0)  # 2 esperas de 3 s
        client.publish_instagram_container.assert_called_once_with(self.ig.external_id, "tok", "c-1")

    def test_AC_14_permalink_failure_still_publishes(self):
        client = graph_mock()
        client.get_instagram_permalink.side_effect = MetaApiError("x", code="timeout")
        outcome = self.run_publish(client)
        self.assertEqual((outcome.post_id, outcome.permalink), ("m-1", ""))

    def test_AC_14_already_published_container_is_not_republished(self):
        client = graph_mock(["PUBLISHED"])
        outcome = self.run_publish(client)
        self.assertEqual((outcome.post_id, outcome.permalink), ("", ""))
        client.publish_instagram_container.assert_not_called()

    def test_AC_15_error_and_expired_raise_container_failed_without_publishing(self):
        for status in ("ERROR", "EXPIRED"):
            self.target.external_container_id = ""
            client = graph_mock([status])
            with self.assertLogs("apps.social.meta", level="WARNING") as logs:
                with self.assertRaises(instagram_publish.ContainerFailed) as ctx:
                    self.run_publish(client)
            self.assertEqual(ctx.exception.status, status)
            self.assertIn(f"instagram_container_error target={self.target.pk} code={status}", "\n".join(logs.output))
            client.publish_instagram_container.assert_not_called()

    def test_AC_16_wait_exhausted_raises_not_ready_and_keeps_the_container(self):
        client = graph_mock(["IN_PROGRESS"])
        with self.assertRaises(instagram_publish.ContainerNotReady):
            self.run_publish(client)
        self.target.refresh_from_db()
        self.assertEqual(self.target.external_container_id, "c-1")
        self.assertGreaterEqual(self.clock.t, 60)
        client.publish_instagram_container.assert_not_called()

    def test_AC_20_wait_is_limited_by_the_remaining_budget(self):
        client = graph_mock(["IN_PROGRESS"])
        with self.assertRaises(instagram_publish.ContainerNotReady):
            self.run_publish(client, max_wait=10)
        self.assertLess(self.clock.t, 15)

    def test_AC_17_resume_reuses_the_container(self):
        self.target.external_container_id = "c-old"
        client = graph_mock()
        outcome = self.run_publish(client)
        client.create_instagram_container.assert_not_called()
        self.assertEqual(self.urls, 0)
        client.instagram_container_status.assert_called_with("c-old", "tok")
        self.assertEqual(outcome.post_id, "m-1")


@override_settings(**SETTINGS)
class InstagramDispatchTests(PublicationTestMixin, TestCase):
    """Alvo completo: reivindicação, despacho, estado final e mensagens."""

    def setUp(self):
        super().setUp()
        self.page = make_page(self.alice, "50")
        self.ig = make_instagram(self.alice, self.page)
        self.fb = self.make_accounts(1)[0]
        self.publication = publishing.create_publication(self.alice, CAPTION, sanitize_image(make_upload()), [self.ig])
        self.target = self.publication.targets.get()
        self.sleep = mock.patch("apps.social.services.instagram_publish.time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def run_target(self, client):
        return publishing.process_target(self.target.pk, publishing.ClientPool(graph=client))

    def test_AC_14_publishes_and_records_the_result(self):
        self.assertEqual(self.run_target(graph_mock()), S.PUBLISHED)
        self.target.refresh_from_db()
        self.assertEqual((self.target.external_post_id, self.target.permalink, self.target.error_message), ("m-1", PERMALINK, ""))
        self.assertIsNotNone(self.target.published_at)
        self.assertEqual(self.publication.status, "published")

    def test_AC_15_container_error_fails_discards_the_id_and_never_publishes(self):
        client = graph_mock(["ERROR"])
        self.assertEqual(self.run_target(client), S.FAILED)
        self.target.refresh_from_db()
        self.assertEqual(self.target.error_message, publishing.MSG_IG_IMAGE_REJECTED)
        self.assertEqual((self.target.external_container_id, self.target.error_code), ("", "error"))
        client.publish_instagram_container.assert_not_called()
        # o próximo envio cria outro container, com nova URL
        publishing.requeue_target(self.target.pk)
        client2 = graph_mock()
        self.assertEqual(self.run_target(client2), S.PUBLISHED)
        client2.create_instagram_container.assert_called_once()

    def test_AC_16_wait_exhausted_fails_keeps_container_and_retry_reuses_it(self):
        with override_settings(INSTAGRAM_CONTAINER_WAIT_SECONDS=0):
            client = graph_mock(["IN_PROGRESS"])
            self.assertEqual(self.run_target(client), S.FAILED)
        self.target.refresh_from_db()
        self.assertEqual((self.target.error_message, self.target.external_container_id), (publishing.MSG_IG_PENDING, "c-1"))
        publishing.requeue_target(self.target.pk)
        client2 = graph_mock()
        self.assertEqual(self.run_target(client2), S.PUBLISHED)
        client2.create_instagram_container.assert_not_called()  # AC-17

    def test_AC_18_media_publish_without_response_becomes_uncertain_and_keeps_the_container(self):
        client = graph_mock()
        client.publish_instagram_container.side_effect = MetaApiError("x", code="timeout", outcome_unknown=True)
        self.assertEqual(self.run_target(client), S.UNCERTAIN)
        self.target.refresh_from_db()
        self.assertEqual((self.target.error_code, self.target.error_message), ("timeout", publishing.MSG_UNCERTAIN))
        self.assertEqual(self.target.external_container_id, "c-1")
        self.assertTrue(self.target.is_resolvable)
        # nunca é reenviado sozinho
        publishing.send_pending(self.publication, client=client)
        self.assertEqual(client.publish_instagram_container.call_count, 1)

    def test_AC_18_uncertain_is_resolved_like_other_platforms(self):
        client = graph_mock()
        client.publish_instagram_container.side_effect = MetaApiError("x", code="interrupted", outcome_unknown=True)
        self.run_target(client)
        self.assertTrue(publishing.resolve_as_published(self.target.pk))
        self.target.refresh_from_db()
        self.assertEqual(self.target.status, S.PUBLISHED)

    def test_AC_18_container_creation_failure_is_a_certain_failure_not_uncertain(self):
        client = graph_mock()
        client.create_instagram_container.side_effect = MetaApiError("x", code="timeout")
        self.assertEqual(self.run_target(client), S.FAILED)

    def test_AC_20_inline_mode_uses_the_same_publisher(self):
        client = graph_mock()
        result = publishing.send_pending(self.publication, client=client)
        self.assertEqual((result.published, result.failed, result.uncertain), (1, 0, 0))
        self.target.refresh_from_db()
        self.assertEqual((self.target.status, self.target.external_post_id), (S.PUBLISHED, "m-1"))

    def test_AC_10_mixed_targets_are_independent(self):
        pub = publishing.create_publication(self.alice, CAPTION, sanitize_image(make_upload()), [self.ig, self.fb])
        client = graph_mock(["ERROR"])
        client.publish_photo.return_value = {"photo_id": "p", "post_id": "1_77"}
        publishing.send_pending(pub, client=client)
        states = {t.platform: t.status for t in pub.targets.all()}
        self.assertEqual(states, {"instagram": S.FAILED, "facebook_page": S.PUBLISHED})

    def test_AC_13_without_public_address_fails_without_calling_meta(self):
        client = graph_mock()
        with override_settings(THREADS_REDIRECT_URI="", PUBLIC_BASE_URL=""):
            self.assertEqual(self.run_target(client), S.FAILED)
        client.create_instagram_container.assert_not_called()
        self.target.refresh_from_db()
        self.assertEqual(self.target.error_message, publishing.MSG_IG_NO_PUBLIC_URL)

    def test_AC_13_missing_image_file_fails_without_calling_meta(self):
        self.publication.image.delete(save=False)
        client = graph_mock()
        self.assertEqual(self.run_target(client), S.FAILED)
        client.create_instagram_container.assert_not_called()
