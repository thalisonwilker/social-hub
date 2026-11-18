from unittest import mock

import requests
from django.test import TestCase, override_settings

from apps.social.images import sanitize_image
from apps.social.models import PublicationTarget, SocialAccount
from apps.social.services import publishing
from apps.social.services.meta import MetaApiError

from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_instagram_model import make_instagram, make_page
from .test_instagram_publisher import SETTINGS, graph_mock

S = PublicationTarget.Status
RAW = "TEXTO-CRU-DA-META-SECRETO"


@override_settings(**SETTINGS)
class InstagramErrorTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.page = make_page(self.alice, "50")
        self.ig = make_instagram(self.alice, self.page)
        self.publication = publishing.create_publication(self.alice, "Legenda", sanitize_image(make_upload()), [self.ig])
        self.target = self.publication.targets.get()
        mock.patch("apps.social.services.instagram_publish.time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def fail_with(self, error, *, at="create_instagram_container"):
        client = graph_mock()
        getattr(client, at).side_effect = error
        status = publishing.process_target(self.target.pk, publishing.ClientPool(graph=client))
        self.target.refresh_from_db()
        return status, client

    def test_AC_19_token_error_marks_instagram_and_page_for_reauth(self):
        for code in (102, 190):
            self.target.refresh_from_db()
            publishing.requeue_target(self.target.pk) if self.target.status == S.FAILED else None
            SocialAccount.objects.update(status=SocialAccount.Status.ACTIVE)
            status, _ = self.fail_with(MetaApiError(RAW, code=code))
            self.assertEqual(status, S.FAILED)
            self.assertEqual(self.target.error_message, publishing.MSG_IG_REAUTH)
            for account in (self.ig, self.page):
                account.refresh_from_db()
                self.assertEqual(account.status, SocialAccount.Status.NEEDS_REAUTH)
                self.assertTrue(account.last_error.startswith("Meta erro"))

    def test_AC_19_token_error_at_publish_step_is_a_certain_failure(self):
        status, _ = self.fail_with(MetaApiError(RAW, code=190, status=400), at="publish_instagram_container")
        self.assertEqual(status, S.FAILED)  # a Meta respondeu: não publicou

    def test_AC_19_friendly_messages_never_show_the_raw_text(self):
        cases = {
            10: publishing.MSG_PERMISSION,
            200: publishing.MSG_PERMISSION,
            4: publishing.MSG_RATE_LIMIT,
            9: publishing.MSG_RATE_LIMIT,
            368: publishing.MSG_BLOCKED,
            "network": publishing.MSG_NETWORK,
            "timeout": publishing.MSG_NETWORK,
        }
        for code, expected in cases.items():
            with self.subTest(code=code):
                self.target.refresh_from_db()
                if self.target.status == S.FAILED:
                    publishing.requeue_target(self.target.pk)
                status, _ = self.fail_with(MetaApiError(RAW, code=code))
                self.assertEqual((status, self.target.error_message), (S.FAILED, expected))
                self.assertNotIn(RAW, self.target.error_message)

    def test_AC_19_unknown_code_gets_a_generic_message(self):
        status, _ = self.fail_with(MetaApiError(RAW, code=2207026))
        self.assertEqual(status, S.FAILED)
        self.assertNotIn(RAW, self.target.error_message)
        self.assertIn("2207026", self.target.error_message)

    def test_AC_19_account_in_reauth_never_calls_meta(self):
        SocialAccount.objects.filter(pk=self.ig.pk).update(status=SocialAccount.Status.NEEDS_REAUTH)
        client = graph_mock()
        status = publishing.process_target(self.target.pk, publishing.ClientPool(graph=client))
        self.target.refresh_from_db()
        self.assertEqual((status, self.target.error_message, self.target.error_code), (S.FAILED, publishing.MSG_IG_REAUTH, "reauth"))
        client.create_instagram_container.assert_not_called()

    def test_AC_19_undecryptable_token_fails_with_credentials_message(self):
        SocialAccount.objects.filter(pk=self.ig.pk).update(access_token_enc="lixo")
        client = graph_mock()
        status = publishing.process_target(self.target.pk, publishing.ClientPool(graph=client))
        self.target.refresh_from_db()
        self.assertEqual((status, self.target.error_message), (S.FAILED, publishing.MSG_CREDENTIALS))
        client.create_instagram_container.assert_not_called()

    def test_AC_19_not_configured_meta_fails_without_calling(self):
        client = graph_mock()
        with override_settings(META_APP_ID=""):
            status = publishing.process_target(self.target.pk, publishing.ClientPool(graph=client))
        self.assertEqual(status, S.FAILED)
        client.create_instagram_container.assert_not_called()

    def test_AC_19_failed_target_can_be_retried_and_publishes(self):
        self.fail_with(MetaApiError(RAW, code=4))
        self.assertTrue(self.target.can_try_again)
        self.assertTrue(publishing.requeue_target(self.target.pk))
        status = publishing.process_target(self.target.pk, publishing.ClientPool(graph=graph_mock()))
        self.assertEqual(status, S.PUBLISHED)
