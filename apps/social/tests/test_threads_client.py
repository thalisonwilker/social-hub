import logging
from unittest import mock
from urllib.parse import parse_qs, urlparse

import requests
from django.test import SimpleTestCase

from apps.social.services.meta import MetaApiError
from apps.social.services.threads import ThreadsClient

from .test_meta_client import FakeResponse

APP_SECRET = "threads-secret-ZZZ"
SHORT = "short-token-111"
LONG = "long-token-222"
CODE = "auth-code-333"
TEXT = "Texto confidencial do post no Threads"


def make_client(*responses):
    session = mock.Mock()
    session.request.side_effect = list(responses)
    client = ThreadsClient(
        app_id="1602810271151684", app_secret=APP_SECRET,
        redirect_uri="https://abc.trycloudflare.com/contas/threads/callback/", version="v1.0", session=session,
    )
    return client, session


def last(session, index=-1):
    call = session.request.call_args_list[index]
    return call.args, call.kwargs


class ThreadsClientTests(SimpleTestCase):
    def test_AC_2_login_url_uses_threads_com_with_required_parameters(self):
        """AC-2: a URL de login usa threads.com e envia client_id, redirect_uri, scope, response_type e state."""
        client, _ = make_client()
        url = urlparse(client.login_url("estado-xyz"))
        self.assertEqual(f"{url.scheme}://{url.netloc}{url.path}", "https://threads.com/oauth/authorize")
        q = parse_qs(url.query)
        self.assertEqual(q["client_id"], ["1602810271151684"])
        self.assertEqual(q["scope"], ["threads_basic,threads_content_publish"])
        self.assertEqual(q["response_type"], ["code"])
        self.assertEqual(q["state"], ["estado-xyz"])
        self.assertEqual(q["redirect_uri"], ["https://abc.trycloudflare.com/contas/threads/callback/"])
        self.assertNotIn(APP_SECRET, url.query)

    def test_AC_4_exchange_code_posts_secret_and_code_in_the_body_unversioned(self):
        """AC-4: troca do code é POST em graph.threads.com/oauth/access_token, com secret e code só no corpo."""
        client, session = make_client(FakeResponse({"access_token": SHORT, "user_id": 17841405793187218}))
        result = client.exchange_code(CODE)
        self.assertEqual(result, {"access_token": SHORT, "user_id": "17841405793187218"})
        (method, url), kwargs = last(session)
        self.assertEqual((method, url), ("POST", "https://graph.threads.com/oauth/access_token"))
        self.assertEqual(kwargs["data"]["code"], CODE)
        self.assertEqual(kwargs["data"]["client_secret"], APP_SECRET)
        self.assertEqual(kwargs["data"]["grant_type"], "authorization_code")
        self.assertEqual(kwargs["data"]["redirect_uri"], "https://abc.trycloudflare.com/contas/threads/callback/")
        self.assertIsNone(kwargs.get("params"))
        for secret in (CODE, APP_SECRET):
            self.assertNotIn(secret, url)
        self.assertEqual(kwargs["headers"], {})  # Bearer não é documentado para o Threads

    def test_AC_4_extend_token_is_a_get_with_expiry_unversioned(self):
        """AC-4: token longo via GET th_exchange_token; devolve expires_in como inteiro."""
        client, session = make_client(FakeResponse({"access_token": LONG, "token_type": "bearer", "expires_in": 5183944}))
        self.assertEqual(client.extend_token(SHORT), {"access_token": LONG, "expires_in": 5183944})
        (method, url), kwargs = last(session)
        self.assertEqual((method, url), ("GET", "https://graph.threads.com/access_token"))
        self.assertEqual(kwargs["params"], {"grant_type": "th_exchange_token", "client_secret": APP_SECRET, "access_token": SHORT})
        for secret in (SHORT, APP_SECRET):
            self.assertNotIn(secret, url)  # vão em params, nunca montados na URL por nós

    def test_AC_12_refresh_token_is_a_get_unversioned(self):
        """AC-12: renovação via GET th_refresh_token com o token vigente."""
        client, session = make_client(FakeResponse({"access_token": "novo-token", "expires_in": 5184000}))
        self.assertEqual(client.refresh_token(LONG), {"access_token": "novo-token", "expires_in": 5184000})
        (method, url), kwargs = last(session)
        self.assertEqual((method, url), ("GET", "https://graph.threads.com/refresh_access_token"))
        self.assertEqual(kwargs["params"], {"grant_type": "th_refresh_token", "access_token": LONG})

    def test_AC_8_missing_fields_in_token_responses_are_errors(self):
        """AC-8: resposta sem token, sem user_id ou sem expires_in vira MetaApiError."""
        for call, payload in (
            (lambda c: c.exchange_code(CODE), {"user_id": 1}),
            (lambda c: c.exchange_code(CODE), {"access_token": SHORT}),
            (lambda c: c.extend_token(SHORT), {"access_token": LONG}),
            (lambda c: c.refresh_token(LONG), {"access_token": LONG, "expires_in": "abc"}),
        ):
            client, _ = make_client(FakeResponse(payload))
            with self.assertRaises(MetaApiError):
                call(client)

    def test_AC_4_profile_is_versioned_and_normalized(self):
        """AC-4: o perfil é lido em /v1.0/{user_id} com os campos id, username, name e foto."""
        payload = {"id": "123", "username": "maria", "name": "Maria", "threads_profile_picture_url": "https://img/x"}
        client, session = make_client(FakeResponse(payload))
        self.assertEqual(client.get_profile("123", LONG),
                         {"id": "123", "username": "maria", "name": "Maria", "picture_url": "https://img/x"})
        (method, url), kwargs = last(session)
        self.assertEqual((method, url), ("GET", "https://graph.threads.com/v1.0/123"))
        self.assertEqual(kwargs["params"]["fields"], "id,username,name,threads_profile_picture_url")
        self.assertEqual(kwargs["params"]["access_token"], LONG)
        self.assertNotIn(LONG, url)

    def test_AC_17_create_text_container_posts_text_and_token_in_the_body(self):
        """AC-17: container TEXT por POST /v1.0/{user_id}/threads com text e access_token no corpo."""
        client, session = make_client(FakeResponse({"id": "container-9"}))
        self.assertEqual(client.create_text_container("123", LONG, TEXT), "container-9")
        (method, url), kwargs = last(session)
        self.assertEqual((method, url), ("POST", "https://graph.threads.com/v1.0/123/threads"))
        self.assertEqual(kwargs["data"], {"media_type": "TEXT", "text": TEXT, "access_token": LONG})
        self.assertIsNone(kwargs.get("params"))
        self.assertNotIn(TEXT, url)
        self.assertNotIn(LONG, url)

    def test_AC_17_container_status_publish_and_permalink(self):
        """AC-17: status por GET, publicação por POST com creation_id, permalink por GET."""
        client, session = make_client(
            FakeResponse({"status": "FINISHED", "id": "c9"}),
            FakeResponse({"id": "media-77"}),
            FakeResponse({"permalink": "https://www.threads.com/@maria/post/abc"}),
        )
        self.assertEqual(client.container_status("c9", LONG), {"status": "FINISHED", "error_message": ""})
        self.assertEqual(client.publish_container("123", LONG, "c9"), "media-77")
        self.assertEqual(client.get_permalink("media-77", LONG), "https://www.threads.com/@maria/post/abc")
        calls = [(c.args, c.kwargs) for c in session.request.call_args_list]
        self.assertEqual(calls[0][0], ("GET", "https://graph.threads.com/v1.0/c9"))
        self.assertEqual(calls[0][1]["params"]["fields"], "status,error_message")
        self.assertEqual(calls[1][0], ("POST", "https://graph.threads.com/v1.0/123/threads_publish"))
        self.assertEqual(calls[1][1]["data"], {"creation_id": "c9", "access_token": LONG})
        self.assertEqual(calls[2][0], ("GET", "https://graph.threads.com/v1.0/media-77"))

    def test_AC_17_missing_ids_are_errors_and_missing_permalink_is_empty(self):
        """AC-17: container/publicação sem id é erro; permalink ausente vira string vazia."""
        client, _ = make_client(FakeResponse({}), FakeResponse({}))
        with self.assertRaises(MetaApiError):
            client.create_text_container("123", LONG, "x")
        with self.assertRaises(MetaApiError):
            client.publish_container("123", LONG, "c")
        client, _ = make_client(FakeResponse({"id": "m"}))
        self.assertEqual(client.get_permalink("m", LONG), "")

    def test_AC_20_error_shapes_are_mapped_and_sanitized(self):
        """AC-20: erro aninhado (Graph) e erro de topo (OAuth do Threads) viram MetaApiError sem texto cru."""
        nested = {"error": {"message": f"token {LONG} {TEXT}", "code": 190, "error_subcode": 463}}
        flat = {"error_type": "OAuthException", "code": 400, "error_message": f"codigo {CODE} usado"}
        for payload, status, code in ((nested, 400, 190), (flat, 400, 400)):
            client, _ = make_client(FakeResponse(payload, status=status))
            with self.assertRaises(MetaApiError) as ctx:
                client.exchange_code(CODE)
            self.assertEqual(ctx.exception.code, code)
            for secret in (LONG, TEXT, CODE):
                self.assertNotIn(secret, str(ctx.exception))

    def test_AC_20_token_error_by_code_or_http_401(self):
        """AC-20: código 190/102 ou HTTP 401 contam como erro de token; outros não."""
        for payload, status, expected in (
            ({"error": {"code": 190}}, 400, True), ({"error": {"code": 102}}, 400, True),
            ({"error": {"message": "x"}}, 401, True), ({"error": {"code": 4}}, 400, False),
        ):
            client, _ = make_client(FakeResponse(payload, status=status))
            with self.assertRaises(MetaApiError) as ctx:
                client.get_profile("1", LONG)
            self.assertEqual(ctx.exception.is_token_error, expected, (payload, status))

    def test_AC_20_network_error_and_invalid_json(self):
        """AC-20: falha de rede e resposta inválida viram erros reenviáveis (network/bad_response)."""
        client, _ = make_client(requests.ConnectionError(f"falha {LONG}"))
        with self.assertRaises(MetaApiError) as ctx:
            client.get_profile("1", LONG)
        self.assertEqual(ctx.exception.code, "network")
        self.assertNotIn(LONG, str(ctx.exception))
        client, _ = make_client(FakeResponse(None, json_error=True))
        with self.assertRaises(MetaApiError) as ctx:
            client.get_profile("1", LONG)
        self.assertEqual(ctx.exception.code, "bad_response")

    def test_AC_25_logs_never_contain_urls_params_tokens_or_text(self):
        """AC-25: o log de erro registra só endpoint/código, nunca token, segredo, code nem texto."""
        client, _ = make_client(FakeResponse({"error": {"code": 100, "message": f"{LONG} {APP_SECRET} {TEXT}"}}, status=400))
        with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs, self.assertRaises(MetaApiError):
            client.create_text_container("123", LONG, TEXT)
        output = "\n".join(logs.output)
        self.assertIn("graph_error", output)
        for secret in (LONG, APP_SECRET, TEXT, "https://", "access_token"):
            self.assertNotIn(secret, output)
