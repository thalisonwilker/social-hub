"""Segurança transversal da publicação (AC-17 a AC-20): roda o fluxo REAL e intercepta só o transporte HTTP."""
import logging
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from apps.social.models import PublicationTarget

from .helpers import KEY, SECRET
from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_meta_client import FakeResponse

TEXT = "Texto-secreto-da-publicacao-XYZ"
S = PublicationTarget.Status


class SecurityFlowTests(PublicationTestMixin, TestCase):
    mock_publish_photo = False  # usa o GraphClient de verdade

    def setUp(self):
        super().setUp()
        self.calls = []
        self.responses = None
        patcher = mock.patch("requests.Session.request", autospec=True, side_effect=self.fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_request(self, session, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.responses:
            return self.responses.pop(0)
        page = url.rsplit("/", 2)[-2]
        return FakeResponse({"id": "photo", "post_id": f"{page}_9"})

    def run_flow(self):
        accounts = self.make_accounts(2)
        pages = []
        response = self.client.post(
            reverse("social:post_new"), {"text": TEXT, "accounts": [a.pk for a in accounts], "image": make_upload()}, follow=True
        )
        pages.append(response)
        pub_id = response.redirect_chain[-1][0].rstrip("/").split("/")[-1]
        for name, args in (("social:post_new", []), ("social:posts", []), ("social:post_detail", [pub_id]), ("social:accounts", [])):
            pages.append(self.client.get(reverse(name, args=args)))
        return pages

    def test_AC_19_tokens_and_secret_never_appear_in_urls_or_params_only_in_headers(self):
        self.run_flow()
        self.assertEqual(len(self.calls), 2)
        for method, url, kwargs in self.calls:
            page = url.rsplit("/", 2)[-2]
            self.assertEqual(method, "POST")
            self.assertTrue(url.endswith(f"/v27.0/{page}/photos"))
            for secret in ("token-1", "token-2", SECRET, KEY, TEXT):
                self.assertNotIn(secret, url)
                self.assertNotIn(secret, str(kwargs.get("params")))
            self.assertEqual(kwargs["headers"], {"Authorization": f"Bearer token-{page}"})
            self.assertEqual(kwargs["data"]["message"], TEXT)  # o texto vai no corpo, nunca na URL
            self.assertIn("source", kwargs["files"])

    def test_AC_19_no_html_response_contains_tokens_secrets_or_encrypted_blobs(self):
        pages = self.run_flow()
        blobs = list(self.alice.social_accounts.values_list("access_token_enc", flat=True))
        for response in pages:
            html = response.content.decode()
            for secret in ("token-1", "token-2", SECRET, KEY, *blobs):
                self.assertNotIn(secret, html)

    def test_AC_19_logs_never_contain_the_publication_text_or_tokens(self):
        with self.assertLogs("apps.social", level=logging.INFO) as logs:
            self.run_flow()
        output = "\n".join(logs.output)
        for secret in (TEXT, "token-1", "token-2", SECRET, KEY):
            self.assertNotIn(secret, output)
        for event in ("publication_created", "publish_ok", "publish_batch"):
            self.assertIn(event, output)

    def test_AC_19_raw_meta_error_text_never_reaches_html_database_or_logs(self):
        leaky = {"error": {"code": 100, "message": f"vazou token-1 {SECRET} {TEXT}"}}
        self.responses = [FakeResponse(leaky, status=400), FakeResponse(leaky, status=400)]
        with self.assertLogs("apps.social", level=logging.INFO) as logs:
            pages = self.run_flow()
        for target in PublicationTarget.objects.all():
            self.assertEqual(target.status, S.FAILED)
            self.assertEqual(target.error_message, "A Meta recusou a publicação (código 100).")
        combined = "\n".join(logs.output) + "".join(r.content.decode() for r in pages)
        for secret in ("vazou", "token-1", SECRET):
            self.assertNotIn(secret, combined)
        self.assertNotIn(TEXT, "\n".join(logs.output))

    def test_AC_19_models_never_expose_text_or_tokens_in_str(self):
        pub = self.make_publication(text=TEXT)
        for obj in (pub, pub.targets.first(), self.alice.social_accounts.first()):
            self.assertNotIn(TEXT, f"{obj!s} {obj!r}")
            self.assertNotIn("token-", f"{obj!s} {obj!r}")

    def test_AC_17_uploaded_original_filename_never_reaches_storage_or_meta(self):
        accounts = self.make_accounts(1)
        upload = make_upload(name="foto-da-casa-da-maria.jpg")
        self.client.post(reverse("social:post_new"), {"text": "x", "accounts": [accounts[0].pk], "image": upload})
        filename = self.calls[0][2]["files"]["source"][0]
        self.assertNotIn("maria", filename)
        self.assertRegex(filename, r"^[0-9a-f]{32}\.jpg$")


class AccessControlTests(PublicationTestMixin, TestCase):
    def test_AC_20_every_publication_route_redirects_anonymous_users_to_login(self):
        pub = self.make_publication()
        self.client.logout()
        routes = [
            ("get", "social:posts", []), ("get", "social:post_new", []), ("post", "social:post_new", []),
            ("get", "social:post_detail", [pub.pk]), ("post", "social:post_send", [pub.pk]), ("get", "social:post_image", [pub.pk]),
        ]
        for method, name, args in routes:
            with self.subTest(name=name, method=method):
                url = reverse(name, args=args)
                response = getattr(self.client, method)(url)
                self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}", fetch_redirect_response=False)
        self.publish.assert_not_called()
        self.assertEqual({t.status for t in pub.targets.all()}, {S.PENDING})
