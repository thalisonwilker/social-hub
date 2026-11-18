import os
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services import deletion
from apps.social.services.meta import GraphClient, MetaApiError
from apps.social.services.publishing import ClientPool
from apps.social.services.threads import ThreadsClient

from .evolution_helpers import EVOLUTION_SETTINGS, make_whatsapp_account
from .publication_helpers import PublicationTestMixin
from .test_instagram_model import make_instagram, make_page
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status


def pool(graph=None, threads=None):
    g = graph or mock.create_autospec(GraphClient, instance=True)
    t = threads or mock.create_autospec(ThreadsClient, instance=True)
    return ClientPool(graph=g, threads=t), g, t


@override_settings(**{**THREADS_SETTINGS, **EVOLUTION_SETTINGS})
class DeletionServiceTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.fb = self.make_accounts(1)[0]
        self.th = make_threads_account(self.alice, "900")
        self.wa = make_whatsapp_account(self.alice, "loja", key="k")
        self.ig = make_instagram(self.alice, make_page(self.alice, "50"))

    def pub(self, accounts=None, *, state=S.PUBLISHED, post_id="PID"):
        publication = self.make_publication(accounts or [self.fb])
        publication.targets.update(status=state, external_post_id=post_id if state == S.PUBLISHED else "")
        return publication

    def target(self, publication):
        return publication.targets.select_related("account").first()

    # ---- elegibilidade (matriz) ------------------------------------------------
    def test_AC_8_eligibility_matrix(self):
        t = self.target(self.pub())
        self.assertEqual(deletion.eligibility(t), "")
        cases = [
            ({"deleted_at": timezone.now()}, deletion.ALREADY_DELETED),
            ({"external_post_id": ""}, deletion.NO_POST_ID),
            ({"status": S.FAILED}, deletion.NOT_PUBLISHED),
            ({"status": S.UNCERTAIN}, deletion.NOT_PUBLISHED),
            ({"status": S.PENDING}, deletion.NOT_PUBLISHED),
        ]
        for fields, reason in cases:
            with self.subTest(reason=reason):
                fresh = self.target(self.pub())
                for k, v in fields.items():
                    setattr(fresh, k, v)
                self.assertEqual(deletion.eligibility(fresh), reason)

    def test_AC_8_disconnected_or_reauth_account(self):
        t = self.target(self.pub())
        SocialAccount.objects.filter(pk=self.fb.pk).update(status=SocialAccount.Status.NEEDS_REAUTH)
        self.assertEqual(deletion.eligibility(self.target(self.pub())), deletion.NEEDS_REAUTH)
        PublicationTarget.objects.filter(pk=t.pk).update(account=None)
        t.refresh_from_db()
        self.assertEqual(deletion.eligibility(t), deletion.NO_ACCOUNT)

    def test_AC_7_instagram_and_whatsapp_are_unsupported_and_never_call_the_platform(self):
        for account in (self.ig, self.wa):
            publication = self.pub([account], post_id="X")
            p, g, t = pool()
            result = deletion.delete_on_platform(self.target(publication), p)
            self.assertEqual((result.outcome, result.message), ("refused", deletion.MSG_REFUSED[deletion.UNSUPPORTED]))
            g.delete_post.assert_not_called()
            t.delete_media.assert_not_called()
            self.assertIsNone(self.target(publication).deleted_at)

    # ---- apagar na plataforma ---------------------------------------------------
    def test_AC_5_facebook_success_marks_deleted_and_keeps_published(self):
        publication = self.pub()
        p, g, _ = pool()
        with self.assertLogs("apps.social.meta", level="INFO") as logs:
            result = deletion.delete_on_platform(self.target(publication), p)
        self.assertEqual(result.outcome, "deleted")
        g.delete_post.assert_called_once_with("PID", "token-1")
        t = self.target(publication)
        self.assertEqual((t.status, t.is_deleted), (S.PUBLISHED, True))
        self.assertEqual(publication.status, "published")
        self.assertIn("target_deleted platform=facebook_page result=ok", "\n".join(logs.output))
        self.assertNotIn("PID", "\n".join(logs.output))

    def test_AC_6_threads_success_refreshes_token_check_and_marks_deleted(self):
        publication = self.pub([self.th], post_id="MEDIA9")
        p, _, t = pool()
        result = deletion.delete_on_platform(self.target(publication), p)
        self.assertEqual(result.outcome, "deleted")
        self.assertEqual(t.delete_media.call_args.args[0], "MEDIA9")
        self.assertTrue(self.target(publication).is_deleted)

    def test_AC_8_ineligible_target_does_not_call_the_platform(self):
        publication = self.pub(state=S.FAILED)
        p, g, _ = pool()
        result = deletion.delete_on_platform(self.target(publication), p)
        self.assertEqual(result.outcome, "refused")
        g.delete_post.assert_not_called()

    def test_AC_9_token_error_marks_the_account_for_reauth_and_keeps_the_post(self):
        publication = self.pub()
        p, g, _ = pool()
        g.delete_post.side_effect = MetaApiError("RAW", code=190, status=400)
        result = deletion.delete_on_platform(self.target(publication), p)
        self.assertEqual((result.outcome, result.message), ("failed", "Reconexão necessária para esta Página."))
        self.fb.refresh_from_db()
        self.assertEqual(self.fb.status, SocialAccount.Status.NEEDS_REAUTH)
        self.assertFalse(self.target(publication).is_deleted)

    def test_AC_9_messages_are_friendly_and_never_raw(self):
        cases = [(10, deletion.MSG_DELETE_PERMISSION), (4, "Limite de requisições da Meta. Tente mais tarde."), (368, deletion.MSG_DELETE_FAILED), (9999, deletion.MSG_DELETE_FAILED)]
        for code, expected in cases:
            with self.subTest(code=code):
                publication = self.pub()
                p, g, _ = pool()
                g.delete_post.side_effect = MetaApiError("RAW-TEXT", code=code, status=400)
                result = deletion.delete_on_platform(self.target(publication), p)
                self.assertEqual((result.outcome, result.message), ("failed", expected))
                self.assertNotIn("RAW", result.message)

    def test_AC_9_threads_permission_asks_to_reconnect(self):
        for code in (10, 200, "platform_not_supported"):
            publication = self.pub([self.th], post_id="M")
            p, _, t = pool()
            t.delete_media.side_effect = MetaApiError("RAW", code=code, status=400)
            result = deletion.delete_on_platform(self.target(publication), p)
            self.assertEqual(result.message, deletion.MSG_DELETE_THREADS_PERMISSION, code)

    def test_AC_10_unknown_outcome_never_marks_deleted(self):
        for code in ("timeout", "interrupted", "bad_response"):
            publication = self.pub()
            p, g, _ = pool()
            g.delete_post.side_effect = MetaApiError("RAW", code=code, outcome_unknown=True)
            result = deletion.delete_on_platform(self.target(publication), p)
            self.assertEqual((result.outcome, result.message), ("unknown", deletion.MSG_DELETE_UNKNOWN))
            self.assertFalse(self.target(publication).is_deleted)

    def test_AC_10_retry_after_unknown_is_safe(self):
        publication = self.pub()
        p, g, _ = pool()
        g.delete_post.side_effect = [MetaApiError("x", code="timeout", outcome_unknown=True), True]
        self.assertEqual(deletion.delete_on_platform(self.target(publication), p).outcome, "unknown")
        self.assertEqual(deletion.delete_on_platform(self.target(publication), p).outcome, "deleted")

    def test_AC_11_object_already_gone_counts_as_deleted(self):
        for exc in (MetaApiError("x", code=100, subcode=33, status=400), MetaApiError("x", code=None, status=404)):
            publication = self.pub()
            p, g, _ = pool()
            g.delete_post.side_effect = exc
            result = deletion.delete_on_platform(self.target(publication), p)
            self.assertEqual((result.outcome, result.message), ("already_gone", deletion.MSG_ALREADY_GONE))
            self.assertTrue(self.target(publication).is_deleted)

    # ---- publicação inteira ---------------------------------------------------------
    def test_AC_12_bulk_deletes_each_eligible_target_and_isolates_failures(self):
        publication = self.make_publication([self.fb, self.th, self.ig, self.wa])
        publication.targets.update(status=S.PUBLISHED, external_post_id="ID")
        p, g, t = pool()
        t.delete_media.side_effect = MetaApiError("x", code=4, status=400)
        bulk = deletion.delete_publication_on_platform(publication, p)
        self.assertEqual((bulk.deleted, bulk.failed, bulk.skipped), (1, 1, 2))
        g.delete_post.assert_called_once()
        self.assertEqual(publication.targets.filter(deleted_at__isnull=False).count(), 1)
        self.assertEqual(Publication.objects.count(), 1)  # nada removido do Hub

    # ---- remover do Hub -----------------------------------------------------------------
    def test_AC_1_remove_publication_deletes_rows_and_image_file_without_calling_platforms(self):
        publication = self.pub()
        path = publication.image.path
        self.assertTrue(os.path.exists(path))
        with mock.patch.object(GraphClient, "delete_post") as delete_post, self.assertLogs("apps.social.meta", level="INFO") as logs:
            self.assertTrue(deletion.remove_publication(publication))
        delete_post.assert_not_called()
        self.assertEqual((Publication.objects.count(), PublicationTarget.objects.count()), (0, 0))
        self.assertFalse(os.path.exists(path))
        self.assertIn("publication_removed", "\n".join(logs.output))

    def test_AC_2_sending_blocks_removal_and_pending_goes_along(self):
        publication = self.make_publication([self.fb, self.th])
        publication.targets.filter(platform="threads").update(status=S.SENDING)
        self.assertFalse(deletion.remove_publication(publication))
        self.assertEqual(Publication.objects.count(), 1)
        publication.targets.filter(platform="threads").update(status=S.PENDING)
        self.assertTrue(deletion.remove_publication(publication))  # `pending` na fila sai junto (cancela o envio)
        self.assertEqual(PublicationTarget.objects.count(), 0)

    def test_AC_3_removing_a_target_keeps_the_rest_and_the_last_removes_the_publication(self):
        publication = self.make_publication([self.fb, self.th])
        path = publication.image.path
        first, second = list(publication.targets.order_by("id"))
        self.assertEqual(deletion.remove_target(first), "target")
        self.assertEqual((Publication.objects.count(), PublicationTarget.objects.count()), (1, 1))
        self.assertTrue(os.path.exists(path))
        self.assertEqual(deletion.remove_target(second), "publication")
        self.assertEqual((Publication.objects.count(), PublicationTarget.objects.count()), (0, 0))
        self.assertFalse(os.path.exists(path))

    def test_AC_3_sending_target_cannot_be_removed(self):
        publication = self.make_publication([self.fb])
        publication.targets.update(status=S.SENDING)
        self.assertIsNone(deletion.remove_target(publication.targets.get()))
        self.assertEqual(PublicationTarget.objects.count(), 1)

    def test_AC_1_missing_image_file_does_not_break_the_removal(self):
        publication = self.pub()
        os.remove(publication.image.path)
        self.assertTrue(deletion.remove_publication(publication))
        self.assertEqual(Publication.objects.count(), 0)
