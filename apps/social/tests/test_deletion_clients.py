import logging
from unittest import mock

import requests
from django.test import SimpleTestCase

from apps.social.services.meta import GraphClient, MetaApiError
from apps.social.services.threads import ThreadsClient

from .test_meta_client import FakeResponse

TOKEN = "token-SECRETO-777"
RAW = "CORPO-CRU-SECRETO"


def graph(*responses):
    session = mock.Mock()
    session.request.side_effect = list(responses)
    return GraphClient(app_id="1", app_secret="s", config_id="2", redirect_uri="http://x/cb", version="v27.0", session=session), session


def threads(*responses):
    session = mock.Mock()
    session.request.side_effect = list(responses)
    return ThreadsClient(app_id="1", app_secret="s", redirect_uri="https://x/cb", version="v1.0", session=session), session


class DeletionClientTests(SimpleTestCase):
    def test_AC_5_facebook_delete_uses_delete_with_the_token_in_the_header(self):
        client, session = graph(FakeResponse({"success": True}))
        self.assertTrue(client.delete_post("123_456", TOKEN))
        (method, url), kwargs = session.request.call_args.args, session.request.call_args.kwargs
        self.assertEqual((method, url), ("DELETE", "https://graph.facebook.com/v27.0/123_456"))
        self.assertEqual(kwargs["headers"], {"Authorization": f"Bearer {TOKEN}"})
        self.assertIsNone(kwargs.get("params"))
        self.assertIsNone(kwargs.get("data"))

    def test_AC_6_threads_delete_uses_delete_on_graph_threads_com(self):
        client, session = threads(FakeResponse({"success": True, "deleted_id": "9"}))
        self.assertTrue(client.delete_media("9", TOKEN))
        (method, url), kwargs = session.request.call_args.args, session.request.call_args.kwargs
        self.assertEqual((method, url), ("DELETE", "https://graph.threads.com/v1.0/9"))
        self.assertEqual(kwargs["params"], {"access_token": TOKEN})

    def test_AC_10_success_false_or_missing_is_outcome_unknown(self):
        for body in ({"success": False}, {}):
            for build, call in ((graph, lambda c: c.delete_post("1_2", TOKEN)), (threads, lambda c: c.delete_media("9", TOKEN))):
                client, _ = build(FakeResponse(body))
                with self.assertRaises(MetaApiError) as ctx:
                    call(client)
                self.assertTrue(ctx.exception.outcome_unknown)

    def test_AC_10_timeout_and_interruption_are_outcome_unknown_but_network_is_not(self):
        for exc, unknown in ((requests.ReadTimeout(), True), (requests.ConnectionError("reset"), True), (requests.ConnectTimeout(), False)):
            client, _ = graph(exc)
            with self.assertRaises(MetaApiError) as ctx:
                client.delete_post("1_2", TOKEN)
            self.assertEqual(ctx.exception.outcome_unknown, unknown, exc)

    def test_AC_9_api_errors_carry_code_and_subcode_without_the_raw_text(self):
        client, _ = graph(FakeResponse({"error": {"code": 100, "error_subcode": 33, "message": RAW}}, status=400))
        with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
            with self.assertRaises(MetaApiError) as ctx:
                client.delete_post("1_2", TOKEN)
        self.assertEqual((ctx.exception.code, ctx.exception.subcode, ctx.exception.outcome_unknown), (100, 33, False))
        self.assertNotIn(RAW, " ".join(logs.output) + str(ctx.exception))

    def test_AC_15_tokens_never_reach_logs(self):
        client, _ = threads(FakeResponse({"error": {"code": 190, "message": f"{RAW} {TOKEN}"}}, status=400))
        with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
            with self.assertRaises(MetaApiError):
                client.delete_media("9", TOKEN)
        self.assertNotIn(TOKEN, " ".join(logs.output))
