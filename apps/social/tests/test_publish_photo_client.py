import io
import logging
from unittest import mock

from django.test import SimpleTestCase

from apps.social.services.meta import GraphClient, MetaApiError

from .test_meta_client import FakeResponse, PAGE_TOKEN, SECRET

MESSAGE = "Texto da minha publicação confidencial"


def client_with(*responses):
    session = mock.Mock()
    session.request.side_effect = list(responses)
    client = GraphClient(app_id="123", app_secret=SECRET, config_id="456", redirect_uri="http://x/cb",
                         version="v27.0", timeout=10, upload_timeout=30, session=session)
    return client, session


def publish(client):
    return client.publish_photo("999", PAGE_TOKEN, image=io.BytesIO(b"IMG"), filename="abc.jpg",
                                content_type="image/jpeg", message=MESSAGE)


class PublishPhotoTests(SimpleTestCase):
    def test_AC_3_sends_multipart_with_message_and_bearer_token(self):
        client, session = client_with(FakeResponse({"id": "photo1", "post_id": "999_555"}))
        result = publish(client)
        self.assertEqual(result, {"photo_id": "photo1", "post_id": "999_555"})
        (method, url), kwargs = session.request.call_args.args, session.request.call_args.kwargs
        self.assertEqual((method, url), ("POST", "https://graph.facebook.com/v27.0/999/photos"))
        self.assertEqual(kwargs["data"], {"message": MESSAGE, "published": "true"})
        name, fileobj, ctype = kwargs["files"]["source"]
        self.assertEqual((name, ctype), ("abc.jpg", "image/jpeg"))
        self.assertEqual(kwargs["headers"], {"Authorization": f"Bearer {PAGE_TOKEN}"})
        self.assertEqual(kwargs["timeout"], 30)  # timeout de upload, não o de 10 s

    def test_AC_19_token_and_text_never_go_in_the_url(self):
        client, session = client_with(FakeResponse({"id": "p", "post_id": "1_2"}))
        publish(client)
        url = session.request.call_args.args[1]
        self.assertNotIn(PAGE_TOKEN, url)
        self.assertNotIn(MESSAGE, url)
        self.assertIsNone(session.request.call_args.kwargs.get("params"))

    def test_AC_3_falls_back_to_photo_id_when_post_id_is_missing(self):
        client, _ = client_with(FakeResponse({"id": "photo1"}))
        self.assertEqual(publish(client)["post_id"], "photo1")

    def test_AC_10_missing_identifiers_is_an_error(self):
        client, _ = client_with(FakeResponse({"success": True}))
        with self.assertRaises(MetaApiError):
            publish(client)

    def test_AC_9_token_error_is_flagged(self):
        client, _ = client_with(FakeResponse({"error": {"code": 190, "message": f"{PAGE_TOKEN} {MESSAGE}"}}, status=400))
        with self.assertRaises(MetaApiError) as ctx:
            publish(client)
        self.assertTrue(ctx.exception.is_token_error)
        self.assertNotIn(MESSAGE, str(ctx.exception))
        self.assertNotIn(PAGE_TOKEN, str(ctx.exception))

    def test_AC_19_logs_never_include_text_or_tokens(self):
        client, _ = client_with(FakeResponse({"error": {"code": 368, "message": MESSAGE}}, status=400))
        with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs, self.assertRaises(MetaApiError):
            publish(client)
        output = "\n".join(logs.output)
        self.assertIn("graph_error", output)
        self.assertNotIn(MESSAGE, output)
        self.assertNotIn(PAGE_TOKEN, output)

    def test_existing_calls_keep_the_default_timeout_and_no_files(self):
        client, session = client_with(FakeResponse({"id": "1", "name": "A"}))
        client.get_page("1", PAGE_TOKEN)
        self.assertEqual(session.request.call_args.kwargs["timeout"], 10)
        self.assertIsNone(session.request.call_args.kwargs["files"])
