"""Segurança transversal da imagem no Threads (AC-10, AC-20): fluxo REAL, só o transporte HTTP interceptado.

O falso 'buscador da Meta' faz o GET da URL assinada de verdade (no meio do POST do container), como a Meta faria.
"""
import logging
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.social import public
from apps.social.models import Publication

from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_meta_client import FakeResponse
from .threads_helpers import HOST, THREADS_SETTINGS, make_threads_account

TEXT = "Texto-secreto-da-publicacao-IMG"
PERMALINK = "https://www.threads.com/@maria/post/abc"


@override_settings(**THREADS_SETTINGS)
class ImageSecurityFlowTests(PublicationTestMixin, TestCase):
    mock_publish_photo = False

    def setUp(self):
        super().setUp()
        self.threads = make_threads_account(self.alice, "900")
        self.calls = []
        self.fetched = []
        self.container_status = {"status": "FINISHED"}
        patcher = mock.patch("requests.Session.request", autospec=True, side_effect=self.fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_request(self, session, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        path = urlparse(url).path
        if (method, path) == ("POST", "/v1.0/900/threads"):
            image_url = kwargs["data"]["image_url"]
            parsed = urlparse(image_url)
            response = Client().get(f"{parsed.path}?{parsed.query}", HTTP_HOST=parsed.netloc)  # a "Meta" busca a imagem
            self.fetched.append((image_url, response))
            return FakeResponse({"id": "c-1"})
        table = {
            ("GET", "/v1.0/c-1"): self.container_status,
            ("POST", "/v1.0/900/threads_publish"): {"id": "m-1"},
            ("GET", "/v1.0/m-1"): {"permalink": PERMALINK},
            ("GET", "/refresh_access_token"): {"access_token": "renovado", "expires_in": 5184000},
        }
        if (method, path) in table:
            return FakeResponse(table[(method, path)])
        if method == "POST" and path.endswith("/photos"):
            return FakeResponse({"id": "photo", "post_id": f"{path.split('/')[-2]}_9"})
        raise AssertionError(f"chamada inesperada: {method} {url}")

    def run_flow(self, accounts=None):
        accounts = accounts or [self.threads]
        return self.client.post(
            reverse("social:post_new"),
            {"text": TEXT, "accounts": [a.pk for a in accounts], "image": make_upload()},
            follow=True,
        )

    def token(self):
        return parse_qs(urlparse(self.fetched[0][0]).query)["t"][0]

    def test_AC_20_the_meta_can_fetch_the_image_during_the_send_and_only_then(self):
        """AC-20: durante o envio a URL assinada entrega a imagem (200); depois de publicado, a mesma URL dá 404."""
        self.run_flow()
        image_url, response = self.fetched[0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertTrue(image_url.startswith(f"https://{HOST}/publico/imagem.jpg?t="))
        after = Client().get(urlparse(image_url).path + "?" + urlparse(image_url).query)
        self.assertEqual(after.status_code, 404)  # alvo publicado: a URL fecha antes de expirar

    def test_AC_10_token_travels_only_in_the_post_body_to_the_meta(self):
        """AC-10: o token da imagem vai só no corpo do POST do container; nunca em URL/params de nenhuma chamada."""
        self.run_flow()
        token = self.token()
        for method, url, kwargs in self.calls:
            self.assertNotIn(token, url)
            self.assertNotIn(token, str(kwargs.get("params") or ""))
        bodies = [str(k.get("data")) for m, u, k in self.calls if m == "POST"]
        self.assertEqual(sum(token in b for b in bodies), 1)

    def test_AC_10_token_never_appears_in_logs_html_or_messages(self):
        """AC-10: logs do app, HTML do detalhe/histórico e mensagens ao usuário não trazem o token nem a URL."""
        with self.assertLogs("apps.social", level=logging.INFO) as logs:
            response = self.run_flow()
        token = self.token()
        output = "\n".join(logs.output)
        for secret in (token, "/publico/imagem", TEXT, "https://", "access_token"):
            self.assertNotIn(secret, output)
        pages = [response, self.client.get(reverse("social:posts")), self.client.get(reverse("social:post_new"))]
        for page in pages:
            html = page.content.decode()
            self.assertNotIn(token, html)
            self.assertNotIn("/publico/imagem", html)
        target = Publication.objects.get().targets.get()
        self.assertNotIn(token, f"{target.error_message}{target.external_container_id}{target.permalink}")

    def test_AC_10_failure_messages_do_not_leak_the_url_either(self):
        """AC-10: com container em erro, a mensagem do alvo e o log não trazem token nem URL."""
        self.container_status = {"status": "ERROR", "error_message": "FAILED_DOWNLOADING_IMAGE"}
        with self.assertLogs("apps.social", level=logging.INFO) as logs:
            response = self.run_flow()
        token = self.token()
        target = Publication.objects.get().targets.get()
        self.assertEqual(target.status, "failed")
        self.assertNotIn(token, response.content.decode() + target.error_message + "\n".join(logs.output))
        self.assertIn("code=FAILED_DOWNLOADING_IMAGE", "\n".join(logs.output))

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_AC_20_forged_host_never_changes_the_generated_url(self):
        """AC-20: Host forjado na requisição de envio não altera a base da URL entregue à Meta."""
        self.client.post(
            reverse("social:post_new"),
            {"text": TEXT, "accounts": [self.threads.pk], "image": make_upload()},
            HTTP_HOST="atacante.example",
        )
        image_url = self.fetched[0][0]
        self.assertTrue(image_url.startswith(f"https://{HOST}/"))
        self.assertNotIn("atacante", image_url)

    def test_AC_20_a_token_cannot_fetch_another_publications_image(self):
        """AC-20: o token da publicação A nunca devolve a imagem da publicação B (rota resolve só pelo token)."""
        self.run_flow()
        pub_a = Publication.objects.get()
        pub_b = self.make_publication([self.threads], text="outra")
        pub_b.targets.update(status="pending")
        got = Client().get(f"/publico/imagem.jpg?t={public.sign_image_token(pub_b.pk)}")
        self.assertEqual(b"".join(got.streaming_content), pub_b.image.open("rb").read())
        self.assertNotEqual(pub_a.image.name, pub_b.image.name)
        pub_a_token = public.sign_image_token(pub_a.pk)
        self.assertEqual(Client().get(f"/publico/imagem.jpg?t={pub_a_token}").status_code, 404)  # A já publicada
