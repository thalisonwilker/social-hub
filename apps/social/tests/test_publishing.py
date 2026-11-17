import logging
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.social.crypto import TokenCryptoError
from apps.social.images import sanitize_image
from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services import publishing
from apps.social.services.meta import GraphClient, MetaApiError

from .helpers import KEY, PAGE_TOKEN_1, VALID_META_SETTINGS
from .image_helpers import make_upload

S = PublicationTarget.Status
TEXT = "Texto confidencial da publicação"


@override_settings(**VALID_META_SETTINGS)
class PublishingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice", password="x")

    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        patcher = mock.patch.object(GraphClient, "publish_photo", autospec=True)
        self.publish = patcher.start()
        self.addCleanup(patcher.stop)
        self.publish.side_effect = lambda client, page_id, token, **kw: {"photo_id": "p", "post_id": f"{page_id}_77"}
        self.client_obj = GraphClient.from_settings()

    def accounts(self, n=2):
        out = []
        for i in range(1, n + 1):
            acc = SocialAccount(owner=self.user, platform="facebook_page", external_id=str(i), name=f"Página {i}")
            acc.set_token(f"token-{i}")
            acc.save()
            out.append(acc)
        return out

    def create(self, n=2, text=TEXT):
        accs = self.accounts(n)
        return publishing.create_publication(self.user, text, sanitize_image(make_upload()), accs), accs

    def send(self, pub, **kw):
        return publishing.send_pending(pub, client=self.client_obj, **kw)

    # ---- criação ---------------------------------------------------------
    def test_AC_3_create_makes_one_pending_target_per_page_and_saves_sanitized_image(self):
        pub, _ = self.create(3)
        self.assertEqual(pub.targets.count(), 3)
        self.assertTrue(all(t.status == S.PENDING for t in pub.targets.all()))
        self.assertEqual(pub.image_content_type, "image/jpeg")
        path = Path(self.media) / pub.image.name
        self.assertTrue(path.exists())
        self.assertRegex(path.name, r"^[0-9a-f]{32}\.jpg$")
        self.assertTrue(pub.image.name.startswith("publications/"))

    def test_AC_3_failed_creation_leaves_no_orphan_file(self):
        accs = self.accounts(1)
        with mock.patch.object(PublicationTarget.objects, "bulk_create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                publishing.create_publication(self.user, TEXT, sanitize_image(make_upload()), accs)
        self.assertEqual(Publication.objects.count(), 0)
        self.assertEqual([p for p in Path(self.media).rglob("*") if p.is_file()], [])

    # ---- sucesso ---------------------------------------------------------
    def test_AC_3_send_publishes_each_page_with_its_own_token_and_the_image_file(self):
        pub, _ = self.create(2)
        seen = {}

        def fake(client, page_id, token, *, image, filename, content_type, message):
            seen[page_id] = (token, image.read(4), filename, content_type, message)
            return {"photo_id": "p", "post_id": f"{page_id}_77"}

        self.publish.side_effect = fake
        result = self.send(pub)
        self.assertEqual((result.attempted, result.published, result.failed, result.remaining), (2, 2, 0, 0))
        self.assertEqual(seen["1"][0], "token-1")
        self.assertEqual(seen["2"][0], "token-2")
        self.assertEqual(seen["1"][1][:2], b"\xff\xd8")  # bytes JPEG reais enviados
        self.assertEqual((seen["1"][3], seen["1"][4]), ("image/jpeg", TEXT))
        for t in pub.targets.all():
            self.assertEqual(t.status, S.PUBLISHED)
            self.assertEqual(t.external_post_id, f"{t.page_external_id}_77")
            self.assertEqual(t.permalink, f"https://www.facebook.com/{t.page_external_id}_77")
            self.assertIsNotNone(t.published_at)
            self.assertEqual(t.attempts, 1)
        self.assertEqual(pub.status, Publication.Status.PUBLISHED)

    # ---- falhas ----------------------------------------------------------
    def test_AC_8_partial_failure(self):
        pub, _ = self.create(3)
        self.publish.side_effect = [
            {"photo_id": "p", "post_id": "1_1"}, MetaApiError("x", code=368), {"photo_id": "p", "post_id": "3_3"}]
        result = self.send(pub)
        self.assertEqual((result.published, result.failed), (2, 1))
        statuses = {t.page_external_id: t.status for t in pub.targets.all()}
        self.assertEqual(statuses, {"1": S.PUBLISHED, "2": S.FAILED, "3": S.PUBLISHED})
        self.assertEqual(pub.status, Publication.Status.FAILED)

    def test_AC_9_token_error_marks_account_needs_reauth_and_batch_continues(self):
        pub, accs = self.create(2)
        self.publish.side_effect = [MetaApiError("x", code=190), {"photo_id": "p", "post_id": "2_2"}]
        self.send(pub)
        failed = pub.targets.get(page_external_id="1")
        self.assertEqual((failed.status, failed.error_message), (S.FAILED, publishing.MSG_REAUTH))
        accs[0].refresh_from_db()
        self.assertEqual(accs[0].status, SocialAccount.Status.NEEDS_REAUTH)
        self.assertEqual(pub.targets.get(page_external_id="2").status, S.PUBLISHED)
        accs[1].refresh_from_db()
        self.assertEqual(accs[1].status, SocialAccount.Status.ACTIVE)

    def test_AC_10_error_mapping_table(self):
        cases = [
            (10, publishing.MSG_PERMISSION), (200, publishing.MSG_PERMISSION), (220, publishing.MSG_PERMISSION),
            (4, publishing.MSG_RATE_LIMIT), (17, publishing.MSG_RATE_LIMIT), (32, publishing.MSG_RATE_LIMIT),
            (613, publishing.MSG_RATE_LIMIT), (368, publishing.MSG_BLOCKED),
            ("network", publishing.MSG_NETWORK), ("bad_response", publishing.MSG_NETWORK),
            (100, "A Meta recusou a publicação (código 100)."), (None, "A Meta recusou a publicação."),
        ]
        for code, expected in cases:
            with self.subTest(code=code):
                PublicationTarget.objects.all().delete(); Publication.objects.all().delete(); SocialAccount.objects.all().delete()
                pub, _ = self.create(1)
                self.publish.side_effect = MetaApiError("texto cru da Meta com segredo", code=code)
                self.send(pub)
                target = pub.targets.get()
                self.assertEqual((target.status, target.error_message), (S.FAILED, expected))
                self.assertNotIn("segredo", target.error_message)

    def test_AC_10_token_decrypt_and_missing_image_failures_are_friendly(self):
        pub, accs = self.create(1)
        with mock.patch.object(SocialAccount, "get_token", side_effect=TokenCryptoError("x")):
            self.send(pub)
        self.assertEqual(pub.targets.get().error_message, publishing.MSG_CREDENTIALS)
        (Path(self.media) / pub.image.name).unlink()
        self.send(pub)
        self.assertEqual(pub.targets.get().error_message, publishing.MSG_IMAGE_MISSING)

    # ---- lotes e retry ---------------------------------------------------
    @override_settings(PUBLISH_BATCH_SIZE=5)
    def test_AC_11_batches_of_five_then_continue(self):
        pub, _ = self.create(7)
        first = self.send(pub)
        self.assertEqual((first.attempted, first.remaining), (5, 2))
        self.assertEqual(self.publish.call_count, 5)
        self.assertEqual(pub.targets.filter(status=S.PENDING).count(), 2)
        second = self.send(pub)
        self.assertEqual((second.attempted, second.remaining), (2, 0))
        self.assertEqual(self.publish.call_count, 7)
        self.assertEqual(pub.status, Publication.Status.PUBLISHED)

    def test_AC_12_retry_sends_only_failed_and_pending_never_published(self):
        pub, _ = self.create(3)
        self.publish.side_effect = [{"photo_id": "p", "post_id": "1_1"}, MetaApiError("x", code=4), {"photo_id": "p", "post_id": "3_3"}]
        self.send(pub)
        self.publish.reset_mock()
        self.publish.side_effect = lambda client, page_id, token, **kw: {"photo_id": "p", "post_id": f"{page_id}_ok"}
        result = self.send(pub)
        self.assertEqual(result.attempted, 1)
        self.assertEqual([c.args[1] for c in self.publish.call_args_list], ["2"])  # só a que falhou
        self.assertEqual(pub.targets.get(page_external_id="1").external_post_id, "1_1")  # intacto
        self.assertEqual(pub.targets.get(page_external_id="2").attempts, 2)
        self.publish.reset_mock()
        self.assertEqual(self.send(pub).attempted, 0)  # tudo publicado: nada a enviar
        self.publish.assert_not_called()

    # ---- concorrência ----------------------------------------------------
    def test_AC_13_second_claim_of_the_same_target_gets_nothing(self):
        pub, _ = self.create(1)
        target = pub.targets.get()
        self.assertIsNotNone(publishing.claim_target(target.pk))
        self.assertIsNone(publishing.claim_target(target.pk))  # já está sending
        target.refresh_from_db()
        self.assertEqual((target.status, target.attempts), (S.SENDING, 1))

    def test_AC_13_recent_sending_is_not_sent_but_stale_sending_is_reclaimed(self):
        pub, _ = self.create(1)
        target = pub.targets.get()
        PublicationTarget.objects.filter(pk=target.pk).update(status=S.SENDING, last_attempt_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.send(pub).attempted, 0)
        self.publish.assert_not_called()
        PublicationTarget.objects.filter(pk=target.pk).update(last_attempt_at=timezone.now() - timedelta(minutes=6))
        with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
            result = self.send(pub)
        self.assertEqual(result.published, 1)
        self.assertIn("target_reclaimed", "\n".join(logs.output))

    def test_AC_12_published_target_can_never_be_claimed(self):
        pub, _ = self.create(1)
        self.send(pub)
        self.assertIsNone(publishing.claim_target(pub.targets.get().pk))

    # ---- conta desconectada ---------------------------------------------
    def test_AC_14_disconnected_account_fails_without_calling_meta_and_is_not_retryable(self):
        pub, accs = self.create(2)
        accs[0].delete()
        result = self.send(pub)
        self.assertEqual(result.attempted, 1)
        self.assertEqual([c.args[1] for c in self.publish.call_args_list], ["2"])
        orphan = pub.targets.get(page_external_id="1")
        self.assertEqual((orphan.status, orphan.error_message, orphan.page_name), (S.FAILED, publishing.MSG_DISCONNECTED, "Página 1"))
        self.assertFalse(orphan.is_retryable)
        self.publish.reset_mock()
        self.send(pub)  # de novo: continua sem chamar a Meta para ela
        self.publish.assert_not_called()

    # ---- logs ------------------------------------------------------------
    def test_AC_19_logs_never_contain_text_or_tokens(self):
        pub, _ = self.create(2)
        self.publish.side_effect = [{"photo_id": "p", "post_id": "1_1"}, MetaApiError("tok token-2 " + TEXT, code=190)]
        with self.assertLogs("apps.social.meta", level=logging.INFO) as logs:
            self.send(pub)
        output = "\n".join(logs.output)
        for secret in (TEXT, "token-1", "token-2", PAGE_TOKEN_1, KEY):
            self.assertNotIn(secret, output)
        self.assertIn("publish_ok", output)
        self.assertIn("publish_failed", output)
        self.assertIn("publish_batch", output)
