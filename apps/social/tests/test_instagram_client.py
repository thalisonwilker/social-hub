import logging
from unittest import mock

import requests
from django.test import SimpleTestCase

from apps.social.services.meta import GraphClient, MetaApiError

from .test_meta_client import FakeResponse

TOKEN = "page-token-SECRET"
URL = "https://hub.example/publico/instagram.jpg?t=assinado-SECRETO"
CAPTION = "Legenda confidencial #teste"


def make_client(*responses):
    session = mock.Mock()
    session.request.side_effect = list(responses)
    client = GraphClient(
        app_id="1", app_secret="s", config_id="2", redirect_uri="http://x/cb", version="v27.0", session=session
    )
    return client, session


def call(session, index=-1):
    c = session.request.call_args_list[index]
    return c.args, c.kwargs


class InstagramClientTests(SimpleTestCase):
    def test_AC_13_create_container_posts_url_and_caption_in_the_body_with_header_token(self):
        client, session = make_client(FakeResponse({"id": "9001"}))
        self.assertEqual(client.create_instagram_container("178", TOKEN, URL, CAPTION), "9001")
        (method, url), kwargs = call(session)
        self.assertEqual((method, url), ("POST", "https://graph.facebook.com/v27.0/178/media"))
        self.assertEqual(kwargs["data"], {"image_url": URL, "caption": CAPTION})
        self.assertEqual(kwargs["headers"], {"Authorization": f"Bearer {TOKEN}"})
        self.assertIsNone(kwargs.get("params"))

    def test_AC_14_container_status_reads_status_code(self):
        client, session = make_client(FakeResponse({"status_code": "FINISHED", "id": "9001"}))
        self.assertEqual(client.instagram_container_status("9001", TOKEN), {"status": "FINISHED"})
        (method, url), kwargs = call(session)
        self.assertEqual((method, url), ("GET", "https://graph.facebook.com/v27.0/9001"))
        self.assertEqual(kwargs["params"], {"fields": "status_code"})
        self.assertNotIn(TOKEN, str(kwargs["params"]))

    def test_AC_14_publish_posts_creation_id_and_permalink_is_read(self):
        client, session = make_client(FakeResponse({"id": "555"}), FakeResponse({"permalink": "https://instagram.com/p/x/"}))
        self.assertEqual(client.publish_instagram_container("178", TOKEN, "9001"), "555")
        (method, url), kwargs = call(session)
        self.assertEqual((method, url), ("POST", "https://graph.facebook.com/v27.0/178/media_publish"))
        self.assertEqual(kwargs["data"], {"creation_id": "9001"})
        self.assertEqual(client.get_instagram_permalink("555", TOKEN), "https://instagram.com/p/x/")

    def test_AC_18_publish_without_answer_is_outcome_unknown(self):
        for exc in (requests.ReadTimeout(), requests.ConnectionError("reset")):
            client, _ = make_client(exc)
            with self.assertRaises(MetaApiError) as ctx:
                client.publish_instagram_container("178", TOKEN, "9001")
            self.assertTrue(ctx.exception.outcome_unknown, exc)

    def test_AC_18_publish_accepted_but_without_id_is_outcome_unknown(self):
        client, _ = make_client(FakeResponse({}))
        with self.assertRaises(MetaApiError) as ctx:
            client.publish_instagram_container("178", TOKEN, "9001")
        self.assertTrue(ctx.exception.outcome_unknown)

    def test_AC_13_create_container_failures_are_not_outcome_unknown(self):
        client, _ = make_client(requests.ReadTimeout())
        with self.assertRaises(MetaApiError) as ctx:
            client.create_instagram_container("178", TOKEN, URL, CAPTION)
        self.assertFalse(ctx.exception.outcome_unknown)

    def test_AC_21_nothing_sensitive_is_logged_on_errors(self):
        client, _ = make_client(FakeResponse({"error": {"code": 190, "message": f"bad {TOKEN} {URL}"}}, status=400))
        with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
            with self.assertRaises(MetaApiError) as ctx:
                client.create_instagram_container("178", TOKEN, URL, CAPTION)
        output = " ".join(logs.output) + str(ctx.exception)
        for secret in (TOKEN, URL, CAPTION, "assinado-SECRETO"):
            self.assertNotIn(secret, output)
        self.assertTrue(ctx.exception.is_token_error)
