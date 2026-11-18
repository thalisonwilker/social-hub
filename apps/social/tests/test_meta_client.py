import logging
from unittest import mock

import requests
from django.test import SimpleTestCase

from apps.social.services.meta import GraphClient, MetaApiError

SECRET = "app-secret-XYZ"
USER_TOKEN = "user-token-ABC"
PAGE_TOKEN = "page-token-DEF"


class FakeResponse:
    def __init__(self, payload, status=200, json_error=False):
        self._payload, self.status_code, self._json_error = payload, status, json_error

    def json(self):
        if self._json_error:
            raise ValueError("no json")
        return self._payload


def make_client(*responses):
    session = mock.Mock()
    session.request.side_effect = list(responses)
    client = GraphClient(
        app_id="123", app_secret=SECRET, config_id="456",
        redirect_uri="http://localhost:8080/contas/facebook/callback/", version="v27.0", session=session,
    )
    return client, session


def sent(session, index=0):
    call = session.request.call_args_list[index]
    return call.args, call.kwargs


class GraphClientTests(SimpleTestCase):
    def test_AC_2_login_url_has_required_parameters(self):
        client, _ = make_client()
        url = client.login_url("estado-123")
        self.assertTrue(url.startswith("https://www.facebook.com/v27.0/dialog/oauth?"))
        for fragment in ("client_id=123", "config_id=456", "response_type=code",
                         "override_default_response_type=true", "state=estado-123", "redirect_uri=http"):
            self.assertIn(fragment, url)
        self.assertNotIn(SECRET, url)

    def test_AC_16_exchange_code_posts_secret_and_code_in_body_not_url(self):
        client, session = make_client(FakeResponse({"access_token": USER_TOKEN}))
        token = client.exchange_code("codigo-777")
        self.assertEqual(token, USER_TOKEN)
        (method, url), kwargs = sent(session)
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://graph.facebook.com/v27.0/oauth/access_token")
        self.assertNotIn("codigo-777", url)
        self.assertNotIn(SECRET, url)
        self.assertEqual(kwargs["data"]["code"], "codigo-777")
        self.assertEqual(kwargs["data"]["client_secret"], SECRET)
        self.assertIsNone(kwargs.get("params"))
        self.assertEqual(kwargs["timeout"], 10)

    def test_AC_3_extend_token_uses_fb_exchange_token_in_body(self):
        client, session = make_client(FakeResponse({"access_token": "long-token"}))
        self.assertEqual(client.extend_token(USER_TOKEN), "long-token")
        _, kwargs = sent(session)
        self.assertEqual(kwargs["data"]["grant_type"], "fb_exchange_token")
        self.assertEqual(kwargs["data"]["fb_exchange_token"], USER_TOKEN)

    def test_AC_3_list_pages_normalizes_and_sends_bearer_header(self):
        payload = {"data": [
            {"id": "1", "name": "Loja", "category": "Varejo", "picture": {"data": {"url": "http://img/1"}},
             "access_token": PAGE_TOKEN, "tasks": ["CREATE_CONTENT"], "instagram": None},
            {"id": "2", "name": "Sem token"},
        ]}
        client, session = make_client(FakeResponse(payload))
        pages = client.list_pages(USER_TOKEN)
        self.assertEqual(pages[0], {"id": "1", "name": "Loja", "category": "Varejo", "picture_url": "http://img/1",
                                    "access_token": PAGE_TOKEN, "tasks": ["CREATE_CONTENT"], "instagram": None})
        self.assertIsNone(pages[1]["access_token"])
        (method, url), kwargs = sent(session)
        self.assertEqual(kwargs["headers"], {"Authorization": f"Bearer {USER_TOKEN}"})
        self.assertNotIn(USER_TOKEN, url)
        self.assertNotIn(USER_TOKEN, str(kwargs.get("params")))

    def test_AC_16_pagination_uses_cursor_never_the_next_url(self):
        first = {"data": [{"id": "1", "name": "A"}],
                 "paging": {"cursors": {"after": "CUR1"}, "next": "https://graph.facebook.com/x?access_token=LEAK"}}
        second = {"data": [{"id": "2", "name": "B"}], "paging": {"cursors": {"after": "CUR2"}}}
        client, session = make_client(FakeResponse(first), FakeResponse(second))
        pages = client.list_pages(USER_TOKEN)
        self.assertEqual([p["id"] for p in pages], ["1", "2"])
        _, kwargs = sent(session, 1)
        self.assertEqual(kwargs["params"]["after"], "CUR1")
        for call in session.request.call_args_list:
            self.assertNotIn("LEAK", str(call))

    def test_AC_12_get_page_uses_page_token_header(self):
        client, session = make_client(FakeResponse({"id": "1", "name": "Loja"}))
        self.assertEqual(client.get_page("1", PAGE_TOKEN)["id"], "1")
        (method, url), kwargs = sent(session)
        self.assertEqual(url, "https://graph.facebook.com/v27.0/1")
        self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {PAGE_TOKEN}")

    def test_AC_8_graph_error_is_mapped_and_sanitized(self):
        body = {"error": {"message": f"Invalid token {PAGE_TOKEN} {SECRET}", "code": 190, "error_subcode": 463}}
        client, _ = make_client(FakeResponse(body, status=400))
        with self.assertRaises(MetaApiError) as ctx:
            client.get_page("1", PAGE_TOKEN)
        err = ctx.exception
        self.assertEqual((err.code, err.subcode, err.status), (190, 463, 400))
        self.assertTrue(err.is_token_error)
        self.assertNotIn(PAGE_TOKEN, str(err))
        self.assertNotIn(SECRET, str(err))

    def test_AC_12_non_token_error_is_not_flagged_as_token_error(self):
        client, _ = make_client(FakeResponse({"error": {"code": 4}}, status=400))
        with self.assertRaises(MetaApiError) as ctx:
            client.get_page("1", PAGE_TOKEN)
        self.assertFalse(ctx.exception.is_token_error)

    def test_AC_8_timeout_and_network_errors_become_meta_api_error(self):
        client, _ = make_client(requests.Timeout("lento"))
        with self.assertRaises(MetaApiError) as ctx:
            client.exchange_code("c")
        self.assertEqual(ctx.exception.code, "timeout")  # 0007: leitura esgotada (não é mais `network`)

    def test_AC_8_invalid_json_and_missing_token_become_meta_api_error(self):
        client, _ = make_client(FakeResponse(None, json_error=True))
        with self.assertRaises(MetaApiError):
            client.exchange_code("c")
        client, _ = make_client(FakeResponse({"foo": "bar"}))
        with self.assertRaises(MetaApiError):
            client.exchange_code("c")

    def test_AC_16_errors_are_logged_without_secrets(self):
        body = {"error": {"message": f"{USER_TOKEN} {SECRET}", "code": 190}}
        client, _ = make_client(FakeResponse(body, status=400))
        with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
            with self.assertRaises(MetaApiError):
                client.list_pages(USER_TOKEN)
        output = "\n".join(logs.output)
        self.assertIn("graph_error", output)
        self.assertIn("me/accounts", output)
        self.assertNotIn(USER_TOKEN, output)
        self.assertNotIn(SECRET, output)
