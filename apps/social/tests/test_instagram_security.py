"""Segurança transversal do Instagram (spec 0009, AC-20 e AC-21).

Graph API FALSA no transporte (`requests.Session.request`), com cliente, views, worker e serviços REAIS: confere o que de
fato sairia pela rede e que token, URL assinada e corpo de resposta nunca vazam em log, JSON, HTML ou mensagem."""
import logging
import re
from urllib.parse import parse_qs, urlparse

import requests
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from unittest import mock

from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services import publishing
from apps.social.services.worker import Worker

from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_instagram_model import make_instagram, make_page
from .test_instagram_publisher import SETTINGS
from .test_meta_client import FakeResponse

S = PublicationTarget.Status
CAPTION = "LEGENDA-CONFIDENCIAL-DO-INSTAGRAM-55"
PAGE_TOKEN = "PAGE-TOKEN-SECRETO-INSTAGRAM-901"
RAW = "CORPO-CRU-DA-META-SECRETO-902"
PERMALINK = "https://www.instagram.com/p/ABC/"


class FakeGraph:
    def __init__(self, *, publish="ok", container="FINISHED", raw_error=False):
        self.publish, self.container, self.raw_error, self.calls = publish, container, raw_error, []

    def handle(self, _session, method, url, **kwargs):
        parsed = urlparse(url)
        self.calls.append({"method": method, "url": url, "path": parsed.path, **kwargs})
        path = parsed.path
        if self.raw_error:
            return FakeResponse({"error": {"code": 999, "message": RAW}}, status=400)
        if path.endswith("/media_publish"):
            if self.publish == "timeout":
                raise requests.ReadTimeout(f"Read timed out {RAW}")
            return FakeResponse({"id": "m-1"})
        if path.endswith("/media"):
            return FakeResponse({"id": "c-1"})
        fields = (kwargs.get("params") or {}).get("fields", "")
        if "permalink" in fields:
            return FakeResponse({"permalink": PERMALINK})
        if "status_code" in fields:
            return FakeResponse({"status_code": self.container})
        return FakeResponse({})

    def patch(self):
        return mock.patch.object(requests.Session, "request", autospec=True, side_effect=self.handle)


@override_settings(**SETTINGS, PUBLISH_MODE="worker")
class InstagramSecurityTests(PublicationTestMixin, TestCase):
    mock_publish_photo = False

    def setUp(self):
        super().setUp()
        self.page = make_page(self.alice, "50")
        self.page.set_token(PAGE_TOKEN)
        self.page.save()
        self.ig = make_instagram(self.alice, self.page)
        SocialAccount.objects.filter(pk=self.ig.pk).update(access_token_enc=self.page.access_token_enc)
        mock.patch("apps.social.services.instagram_publish.time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def enqueue(self, client=None):
        data = {"text": CAPTION, "accounts": [str(self.ig.pk)], "image": make_upload(size=(800, 800))}
        (client or self.client).post(reverse("social:post_new"), data)
        return Publication.objects.order_by("-id").first()

    def pages(self, pub):
        urls = [reverse("social:post_detail", args=[pub.pk]), reverse("social:posts"), reverse("social:accounts"),
                reverse("social:post_new")]
        return {u: self.client.get(u).content.decode() for u in urls}

    def assertNoLeak(self, haystack, secrets, where):
        for secret in secrets:
            self.assertNotIn(secret, haystack, f"{secret!r} vazou em {where}")

    def test_AC_21_happy_path_sends_the_token_only_in_the_header_and_leaks_nothing(self):
        pub = self.enqueue()
        fake = FakeGraph()
        with fake.patch(), self.assertLogs(level=logging.DEBUG) as logs:
            Worker(pid=1).run_once()
        target = pub.targets.get()
        self.assertEqual((target.status, target.permalink), (S.PUBLISHED, PERMALINK))

        create = next(c for c in fake.calls if c["path"].endswith("/media") and c["method"] == "POST")
        signed_url = create["data"]["image_url"]
        token_in_url = parse_qs(urlparse(signed_url).query)["t"][0]
        for call in fake.calls:
            self.assertEqual(call["headers"], {"Authorization": f"Bearer {PAGE_TOKEN}"})
            self.assertNotIn(PAGE_TOKEN, call["url"] + str(call.get("params")) + str(call.get("data")))
        self.assertEqual(urlparse(create["url"]).netloc, "graph.facebook.com")
        output = "\n".join(logs.output)
        self.assertNoLeak(output, [PAGE_TOKEN, CAPTION, signed_url, token_in_url], "logs")
        for where, html in self.pages(pub).items():
            self.assertNoLeak(html, [PAGE_TOKEN, signed_url, token_in_url, self.page.access_token_enc], where)
        state = self.client.get(reverse("social:post_state", args=[pub.pk])).content.decode()
        self.assertNoLeak(state, [PAGE_TOKEN, signed_url, token_in_url, CAPTION], "JSON de estado")

    def test_AC_21_raw_meta_errors_never_reach_logs_pages_or_json(self):
        pub = self.enqueue()
        fake = FakeGraph(raw_error=True)
        with fake.patch(), self.assertLogs(level=logging.DEBUG) as logs:
            Worker(pid=1).run_once()
        target = pub.targets.get()
        self.assertEqual(target.status, S.FAILED)
        self.assertNoLeak("\n".join(logs.output), [RAW, PAGE_TOKEN, CAPTION], "logs")
        for where, html in self.pages(pub).items():
            self.assertNoLeak(html, [RAW, PAGE_TOKEN], where)
        self.assertNoLeak(self.client.get(reverse("social:post_state", args=[pub.pk])).content.decode(), [RAW, PAGE_TOKEN], "JSON")
        self.assertNotIn(RAW, target.error_message)

    def test_AC_21_uncertain_flow_never_exposes_exception_text(self):
        pub = self.enqueue()
        fake = FakeGraph(publish="timeout")
        with fake.patch(), self.assertLogs(level=logging.DEBUG) as logs:
            Worker(pid=1).run_once()
        target = pub.targets.get()
        self.assertEqual(target.status, S.UNCERTAIN)
        self.assertNoLeak("\n".join(logs.output), [RAW, PAGE_TOKEN, CAPTION], "logs")
        for where, html in self.pages(pub).items():
            self.assertNoLeak(html, [RAW, PAGE_TOKEN], where)
        # nenhuma nova chamada com efeito depois (nunca reenvia sozinho)
        with FakeGraph().patch():
            Worker(pid=1).run_once()
        self.assertEqual(pub.targets.get().status, S.UNCERTAIN)

    def test_AC_21_users_cannot_see_or_operate_each_others_instagram(self):
        pub = self.enqueue()
        other = Client()
        other.force_login(self.bob)
        target = pub.targets.get()
        for url in (
            reverse("social:post_detail", args=[pub.pk]),
            reverse("social:post_state", args=[pub.pk]),
            reverse("social:post_image", args=[pub.pk]),
        ):
            self.assertEqual(other.get(url).status_code, 404, url)
        for url in (
            reverse("social:post_send", args=[pub.pk]),
            reverse("social:target_resolve", args=[pub.pk, target.pk]),
            reverse("social:account_disconnect", args=[self.ig.pk]),
            reverse("social:account_check", args=[self.ig.pk]),
        ):
            self.assertEqual(other.post(url, {"action": "published"}).status_code, 404, url)
        self.assertTrue(SocialAccount.objects.filter(pk=self.ig.pk).exists())
        # e o formulário de outro usuário não aceita o Instagram alheio
        bob_page = make_page(self.bob, "77")
        make_instagram(self.bob, bob_page, external_id="888", username="bob")
        response = other.post(
            reverse("social:post_new"), {"text": "x", "accounts": [self.ig.pk], "image": make_upload(size=(800, 800))}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Publication.objects.filter(owner=self.bob).count(), 0)

    def test_AC_21_instagram_token_is_stored_encrypted_only(self):
        self.assertNotIn(PAGE_TOKEN, self.ig.access_token_enc)
        self.assertEqual(self.ig.get_token(), PAGE_TOKEN)

    @override_settings(PUBLISH_MODE="inline")
    def test_AC_20_inline_mode_publishes_in_the_request_with_the_same_properties(self):
        fake = FakeGraph()
        with fake.patch(), self.assertLogs(level=logging.DEBUG) as logs:
            self.client.post(
                reverse("social:post_new"),
                {"text": CAPTION, "accounts": [str(self.ig.pk)], "image": make_upload(size=(800, 800))},
                follow=True,
            )
        target = PublicationTarget.objects.get()
        self.assertEqual((target.status, target.permalink), (S.PUBLISHED, PERMALINK))
        self.assertNoLeak("\n".join(logs.output), [PAGE_TOKEN, CAPTION], "logs")
        for call in fake.calls:
            self.assertEqual(call["headers"], {"Authorization": f"Bearer {PAGE_TOKEN}"})
