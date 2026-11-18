"""Segurança transversal da exclusão (spec 0010, AC-9, AC-10 e AC-15): plataformas FALSAS no transporte, clientes/views/serviço REAIS."""
import logging
from urllib.parse import urlparse

import requests
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from unittest import mock

from apps.social.models import Publication, PublicationTarget, SocialAccount

from .publication_helpers import PublicationTestMixin
from .test_meta_client import FakeResponse
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status
FB_TOKEN = "FB-TOKEN-SECRETO-111"
TH_TOKEN = "THREADS-TOKEN-SECRETO-222"
POST_ID = "PAGE_POST-ID-SECRETO-333"
MEDIA_ID = "MEDIA-ID-SECRETO-444"
RAW = "CORPO-CRU-SECRETO-555"
TEXT = "TEXTO-CONFIDENCIAL-DA-PUBLICACAO-66"


class FakePlatforms:
    def __init__(self, mode="ok"):
        self.mode, self.calls = mode, []

    def handle(self, _session, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.mode == "timeout":
            raise requests.ReadTimeout(f"Read timed out {RAW} {FB_TOKEN}")
        if self.mode == "error":
            return FakeResponse({"error": {"code": 999, "message": f"{RAW} {FB_TOKEN} {POST_ID}"}}, status=400)
        return FakeResponse({"success": True})

    def patch(self):
        return mock.patch.object(requests.Session, "request", autospec=True, side_effect=self.handle)


@override_settings(**THREADS_SETTINGS)
class DeletionSecurityTests(PublicationTestMixin, TestCase):
    mock_publish_photo = False

    def setUp(self):
        super().setUp()
        self.fb = self.make_accounts(1)[0]
        self.fb.set_token(FB_TOKEN)
        self.fb.save()
        self.th = make_threads_account(self.alice, "900", token=TH_TOKEN)
        self.pub = self.make_publication([self.fb, self.th], text=TEXT)
        self.pub.targets.filter(platform="facebook_page").update(status=S.PUBLISHED, external_post_id=POST_ID)
        self.pub.targets.filter(platform="threads").update(status=S.PUBLISHED, external_post_id=MEDIA_ID)

    def pages(self):
        urls = [reverse("social:post_detail", args=[self.pub.pk]), reverse("social:posts"), reverse("social:accounts")]
        return {u: self.client.get(u).content.decode() for u in urls}

    def assertNoLeak(self, haystack, secrets, where):
        for secret in secrets:
            self.assertNotIn(secret, haystack, f"{secret!r} vazou em {where}")

    def test_AC_15_tokens_go_only_where_documented_and_nothing_leaks(self):
        fake = FakePlatforms()
        with fake.patch(), self.assertLogs(level=logging.DEBUG) as logs:
            response = self.client.post(reverse("social:post_delete_remote", args=[self.pub.pk]), follow=True)
        self.assertEqual(sorted(urlparse(c["url"]).netloc for c in fake.calls), ["graph.facebook.com", "graph.threads.com"])
        fb = next(c for c in fake.calls if "facebook" in c["url"])
        th = next(c for c in fake.calls if "threads" in c["url"])
        self.assertEqual((fb["method"], th["method"]), ("DELETE", "DELETE"))
        self.assertEqual(fb["headers"], {"Authorization": f"Bearer {FB_TOKEN}"})
        self.assertNotIn(FB_TOKEN, fb["url"] + str(fb.get("params")) + str(fb.get("data")))
        self.assertEqual(th["params"], {"access_token": TH_TOKEN})
        self.assertNotIn(TH_TOKEN, th["url"])
        secrets = [FB_TOKEN, TH_TOKEN, POST_ID, MEDIA_ID, TEXT]
        self.assertNoLeak("\n".join(logs.output), secrets, "logs")
        self.assertNoLeak(response.content.decode().replace(TEXT, ""), [FB_TOKEN, TH_TOKEN, POST_ID, MEDIA_ID, self.fb.access_token_enc], "HTML")

    def test_AC_9_raw_platform_errors_never_reach_logs_pages_or_messages(self):
        fake = FakePlatforms("error")
        with fake.patch(), self.assertLogs(level=logging.DEBUG) as logs:
            response = self.client.post(reverse("social:post_delete_remote", args=[self.pub.pk]), follow=True)
        self.assertNoLeak("\n".join(logs.output), [RAW, FB_TOKEN, TH_TOKEN, POST_ID, MEDIA_ID], "logs")
        self.assertNoLeak(response.content.decode(), [RAW, FB_TOKEN, TH_TOKEN, POST_ID, MEDIA_ID], "HTML")
        self.assertEqual(PublicationTarget.objects.filter(deleted_at__isnull=False).count(), 0)

    def test_AC_10_timeouts_never_mark_deleted_or_leak(self):
        fake = FakePlatforms("timeout")
        with fake.patch(), self.assertLogs(level=logging.DEBUG) as logs:
            response = self.client.post(reverse("social:post_delete_remote", args=[self.pub.pk]), follow=True)
        self.assertNoLeak("\n".join(logs.output), [RAW, FB_TOKEN, TH_TOKEN, POST_ID, MEDIA_ID], "logs")
        self.assertNoLeak(response.content.decode(), [RAW, FB_TOKEN, TH_TOKEN, POST_ID, MEDIA_ID], "HTML")
        self.assertEqual(PublicationTarget.objects.filter(deleted_at__isnull=False).count(), 0)
        self.assertContains(response, "com falha")

    def test_AC_15_other_users_cannot_delete_or_remove_and_nothing_is_called(self):
        other = Client()
        other.force_login(self.bob)
        fake = FakePlatforms()
        with fake.patch():
            for name in ("post_delete_remote", "post_remove"):
                self.assertEqual(other.post(reverse(f"social:{name}", args=[self.pub.pk])).status_code, 404)
            for target in self.pub.targets.all():
                for name in ("target_delete_remote", "target_remove"):
                    self.assertEqual(other.post(reverse(f"social:{name}", args=[self.pub.pk, target.pk])).status_code, 404)
        self.assertEqual(fake.calls, [])
        self.assertEqual((Publication.objects.count(), PublicationTarget.objects.count()), (1, 2))

    def test_AC_15_a_target_of_another_publication_is_not_reachable_through_this_one(self):
        other_pub = self.make_publication([self.make_accounts(1, start=9)[0]])
        foreign = other_pub.targets.get()
        fake = FakePlatforms()
        with fake.patch():
            response = self.client.post(reverse("social:target_delete_remote", args=[self.pub.pk, foreign.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(fake.calls, [])
