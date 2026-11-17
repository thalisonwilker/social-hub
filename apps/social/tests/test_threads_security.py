"""Segurança transversal do Threads (AC-25 e AC-26): roda o fluxo REAL e intercepta só o transporte HTTP."""
import logging
from unittest import mock
from urllib.parse import parse_qs, urlparse

import requests
from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import Publication, PublicationTarget, SocialAccount

from .helpers import KEY
from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_meta_client import FakeResponse
from .threads_helpers import CODE, HOST, LONG, SECRET, SHORT, THREADS_SETTINGS, make_threads_account

TEXT = "Texto-secreto-da-publicacao-THREADS"
PERMALINK = "https://www.threads.com/@maria/post/abc"
ALL_SECRETS = (SHORT, LONG, SECRET, CODE, "token-1", KEY)


@override_settings(**THREADS_SETTINGS)
class ThreadsSecurityFlowTests(PublicationTestMixin, TestCase):
    mock_publish_photo = False  # Facebook também usa o cliente real

    def setUp(self):
        super().setUp()
        self.calls = []
        self.overrides = {}  # (method, sufixo da URL) -> resposta/exceção
        patcher = mock.patch("requests.Session.request", autospec=True, side_effect=self.fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_request(self, session, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        for (m, suffix), outcome in self.overrides.items():
            if m == method and url.endswith(suffix):
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        path = urlparse(url).path
        table = {
            ("POST", "/oauth/access_token"): {"access_token": SHORT, "user_id": 900},
            ("GET", "/access_token"): {"access_token": LONG, "expires_in": 5183944},
            ("GET", "/refresh_access_token"): {"access_token": "token-renovado-9", "expires_in": 5184000},
            ("GET", "/v1.0/900"): {"id": "900", "username": "maria", "name": "Maria"},
            ("POST", "/v1.0/900/threads"): {"id": "c-1"},
            ("GET", "/v1.0/c-1"): {"status": "FINISHED"},
            ("POST", "/v1.0/900/threads_publish"): {"id": "m-1"},
            ("GET", "/v1.0/m-1"): {"permalink": PERMALINK},
        }
        if (method, path) in table:
            return FakeResponse(table[(method, path)])
        if method == "POST" and path.endswith("/photos"):  # Facebook
            return FakeResponse({"id": "photo", "post_id": f"{path.split('/')[-2]}_9"})
        raise AssertionError(f"chamada inesperada: {method} {url}")

    # ---- fluxo completo --------------------------------------------------
    def run_flow(self):
        page = self.make_accounts(1)[0]
        pages = []
        start = self.client.post(reverse("social:threads_connect"), HTTP_HOST=HOST)
        state = parse_qs(urlparse(start["Location"]).query)["state"][0]
        pages.append(self.client.get(reverse("social:threads_callback"), {"code": CODE, "state": state}, HTTP_HOST=HOST, follow=True))
        profile = SocialAccount.objects.get(platform="threads")
        pages.append(self.client.get(reverse("social:accounts")))
        pages.append(self.client.get(reverse("social:post_new")))
        response = self.client.post(
            reverse("social:post_new"), {"text": TEXT, "accounts": [page.pk, profile.pk], "image": make_upload()}, follow=True)
        pages.append(response)
        pub_id = Publication.objects.get().pk
        pages.append(self.client.get(reverse("social:post_detail", args=[pub_id])))
        pages.append(self.client.get(reverse("social:posts")))
        pages.append(self.client.get(reverse("dashboard:index")))
        return pages

    def test_AC_25_urls_never_carry_credentials_code_or_text(self):
        """AC-25: nenhuma URL chamada contém token, secret, code ou texto; code só em POST e Threads sem Bearer."""
        self.run_flow()
        threads_calls = [c for c in self.calls if "threads.com" in c[1]]
        self.assertGreaterEqual(len(threads_calls), 7)
        for method, url, kwargs in threads_calls:
            for secret in (*ALL_SECRETS, TEXT, "access_token=", "client_secret="):
                self.assertNotIn(secret, url)
            self.assertNotIn("Authorization", kwargs["headers"])  # Bearer não é documentado para o Threads
        exchange = next(c for c in threads_calls if c[0] == "POST" and c[1].endswith("/oauth/access_token"))
        self.assertEqual(exchange[2]["data"]["code"], CODE)
        self.assertEqual(exchange[2]["data"]["client_secret"], SECRET)
        self.assertIsNone(exchange[2].get("params"))
        for method, url, kwargs in threads_calls:  # o code nunca aparece fora do POST de troca
            if (method, url) != (exchange[0], exchange[1]):
                self.assertNotIn(CODE, str(kwargs))
        text_calls = [c for c in threads_calls if c[1].endswith("/threads")]
        self.assertEqual(text_calls[0][2]["data"]["text"], TEXT)  # o texto vai no corpo do POST, nunca na URL

    def test_AC_25_no_html_response_contains_tokens_secrets_or_encrypted_blobs(self):
        """AC-25: nenhuma página mostra token curto/longo, secret, code, chave nem o texto cifrado do banco."""
        pages = self.run_flow()
        blobs = list(SocialAccount.objects.values_list("access_token_enc", flat=True))
        for response in pages:
            html = response.content.decode()
            for secret in (*ALL_SECRETS, *blobs):
                self.assertNotIn(secret, html)

    def test_AC_25_logs_never_contain_secrets_text_urls_or_params(self):
        """AC-25: logs do fluxo não trazem tokens, secret, code, texto, URLs nem nomes de parâmetros sensíveis."""
        with self.assertLogs("apps.social", level=logging.INFO) as logs:
            self.run_flow()
        output = "\n".join(logs.output)
        for secret in (*ALL_SECRETS, TEXT, "https://", "access_token", "client_secret"):
            self.assertNotIn(secret, output)
        for event in ("threads_oauth_started", "threads_connected", "threads_image_container_created", "publish_ok", "publish_batch"):
            self.assertIn(event, output)

    def test_AC_25_tokens_are_encrypted_in_the_database_and_never_in_the_session(self):
        """AC-25: token do Threads cifrado no banco; a sessão guarda no máximo o state (nunca tokens, code ou secret)."""
        self.run_flow()
        account = SocialAccount.objects.get(platform="threads")
        self.assertNotIn(LONG, account.access_token_enc)
        self.assertEqual(account.get_token(), LONG)
        stored = " ".join(s.session_data for s in Session.objects.all())
        for secret in (SHORT, LONG, SECRET, CODE):
            self.assertNotIn(secret, stored)

    def test_AC_25_network_error_text_with_url_and_token_is_never_exposed(self):
        """AC-25: a exceção de rede do `requests` costuma trazer a URL com o token; o Hub não repassa nada disso."""
        leak = requests.ConnectionError(f"HTTPSConnectionPool(host='graph.threads.com'): /access_token?access_token={LONG}&client_secret={SECRET}")
        self.overrides[("GET", "/access_token")] = leak
        start = self.client.post(reverse("social:threads_connect"), HTTP_HOST=HOST)
        state = parse_qs(urlparse(start["Location"]).query)["state"][0]
        with self.assertLogs("apps.social", level=logging.INFO) as logs:
            response = self.client.get(reverse("social:threads_callback"), {"code": CODE, "state": state}, HTTP_HOST=HOST, follow=True)
        combined = response.content.decode() + "\n".join(logs.output)
        for secret in (LONG, SECRET, SHORT, CODE, "access_token="):
            self.assertNotIn(secret, combined)
        self.assertContains(response, "Não foi possível concluir a conexão com o Threads")
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_AC_25_raw_meta_error_text_never_reaches_html_database_or_logs(self):
        """AC-25: texto cru de erro da Meta (com tokens e o texto da publicação) nunca chega a tela, banco ou log."""
        make_threads_account(self.alice, "900", token="token-1")
        leaky = {"error": {"code": 100, "message": f"vazou token-1 {SECRET} {TEXT}"}}
        self.overrides[("POST", "/v1.0/900/threads")] = FakeResponse(leaky, status=400)
        profile = SocialAccount.objects.get(platform="threads")
        with self.assertLogs("apps.social", level=logging.INFO) as logs:
            response = self.client.post(
                reverse("social:post_new"), {"text": TEXT, "accounts": [profile.pk]}, follow=True)
        target = PublicationTarget.objects.get()
        self.assertEqual((target.status, target.error_message), ("failed", "A Meta recusou a publicação (código 100)."))
        combined = response.content.decode() + target.error_message + "\n".join(logs.output)
        for secret in ("vazou", "token-1", SECRET):
            self.assertNotIn(secret, combined)
        self.assertNotIn(TEXT, "\n".join(logs.output))

    def test_AC_25_refresh_request_keeps_the_token_out_of_the_url_and_the_logs(self):
        """AC-25: a renovação (GET documentado com token em params) não põe o token na URL nem no log."""
        due = make_threads_account(self.alice, "900", days_left=5, refreshed_hours_ago=48, token="token-antigo-77")
        with self.assertLogs("apps.social", level=logging.INFO) as logs:
            self.client.post(reverse("social:post_new"), {"text": TEXT, "accounts": [due.pk]}, follow=True)
        refresh = next(c for c in self.calls if c[1].endswith("/refresh_access_token"))
        self.assertNotIn("token-antigo-77", refresh[1])
        self.assertEqual(refresh[2]["params"]["access_token"], "token-antigo-77")
        output = "\n".join(logs.output)
        for secret in ("token-antigo-77", "token-renovado-9", TEXT):
            self.assertNotIn(secret, output)
        self.assertIn("threads_token_refreshed", output)
        due.refresh_from_db()
        self.assertEqual(due.get_token(), "token-renovado-9")

    # ---- AC-26 -----------------------------------------------------------
    def test_AC_26_other_users_cannot_use_a_threads_profile_they_do_not_own(self):
        """AC-26: o usuário B não publica no perfil de A (id forjado) nem o vê no formulário."""
        theirs = make_threads_account(self.alice, "900", token="token-1")
        make_threads_account(self.bob, "951", username="do_bob")  # B tem um perfil próprio, então o formulário aparece
        self.client.force_login(self.bob)
        self.assertNotContains(self.client.get(reverse("social:post_new")), "@maria")
        response = self.client.post(reverse("social:post_new"), {"text": TEXT, "accounts": [theirs.pk]})
        self.assertEqual(response.status_code, 200)  # formulário reexibido com erro
        self.assertContains(response, "Seleção de Página inválida")
        self.assertEqual(Publication.objects.count(), 0)
        self.assertEqual([c for c in self.calls if "threads.com" in c[1]], [])

    def test_AC_26_every_threads_route_redirects_anonymous_users_to_login(self):
        """AC-26: rotas do Threads e da publicação exigem login e não chamam a Meta."""
        self.client.logout()
        routes = [("post", reverse("social:threads_connect")), ("get", reverse("social:threads_callback") + f"?code={CODE}&state=x"),
                  ("get", reverse("social:post_new")), ("post", reverse("social:post_new"))]
        for method, url in routes:
            with self.subTest(url=url):
                response = getattr(self.client, method)(url, HTTP_HOST=HOST)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("accounts:login")))
        self.assertEqual(self.calls, [])
