"""Testes transversais de segurança (AC-16 e AC-17): segredos fora de HTML, mensagens, logs e URLs."""
import json
import logging
from unittest import mock

import requests
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import SocialAccount
from apps.social.services.meta import GraphClient, MetaApiError

from .helpers import (PAGE_TOKEN_1, PAGE_TOKEN_2, SECRET, USER_TOKEN, VALID_META_SETTINGS, graph_patches)
from .test_meta_client import FakeResponse

SECRETS = (PAGE_TOKEN_1, PAGE_TOKEN_2, USER_TOKEN, SECRET)


@override_settings(**VALID_META_SETTINGS)
class SecretsNeverLeakTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice", password="x")

    def setUp(self):
        self.client.force_login(self.user)

    def run_full_flow(self):
        """Executa conectar → callback → selecionar → listar, devolvendo todas as respostas HTML."""
        pages = []
        response = self.client.post(reverse("social:facebook_connect"))
        pages.append(response)
        state = self.client.session["fb_oauth_state"]["value"]
        with graph_patches():
            pages.append(self.client.get(reverse("social:facebook_callback"), {"code": "CODE-777", "state": state}, follow=True))
        pages.append(self.client.get(reverse("social:facebook_select")))
        pages.append(self.client.post(reverse("social:facebook_select"), {"pages": ["1", "2"]}, follow=True))
        pages.append(self.client.get(reverse("social:accounts")))
        pages.append(self.client.get(reverse("dashboard:index")))
        return pages

    def test_AC_16_no_secret_in_any_html_response_or_redirect(self):
        for response in self.run_full_flow():
            text = response.content.decode() + str(response.headers)
            for secret in (*SECRETS, "CODE-777"):
                self.assertNotIn(secret, text)

    def test_AC_16_no_secret_in_logs(self):
        with self.assertLogs("apps.social.meta", level=logging.INFO) as logs:
            self.run_full_flow()
        output = "\n".join(logs.output)
        for secret in (*SECRETS, "CODE-777"):
            self.assertNotIn(secret, output)

    def test_AC_16_tokens_are_not_plaintext_in_database_or_session_store(self):
        self.run_full_flow()
        for account in SocialAccount.objects.all():
            for secret in (PAGE_TOKEN_1, PAGE_TOKEN_2):
                self.assertNotIn(secret, account.access_token_enc)
        stored = " ".join(s.session_data for s in Session.objects.all())
        for secret in SECRETS:
            self.assertNotIn(secret, stored)
        # e os tokens continuam recuperáveis pela chave:
        self.assertEqual({a.get_token() for a in SocialAccount.objects.all()}, {PAGE_TOKEN_1, PAGE_TOKEN_2})

    def test_AC_16_pending_session_data_holds_only_encrypted_tokens(self):
        self.client.post(reverse("social:facebook_connect"))
        state = self.client.session["fb_oauth_state"]["value"]
        with graph_patches():
            self.client.get(reverse("social:facebook_callback"), {"code": "c", "state": state})
        pending = self.client.session["fb_pending"]
        self.assertNotIn(PAGE_TOKEN_1, json.dumps(pending))
        self.assertTrue(all(p["token_enc"].startswith("gAAAA") for p in pending["pages"]))  # formato Fernet

    def test_AC_16_failure_paths_do_not_leak_secrets_either(self):
        self.client.post(reverse("social:facebook_connect"))
        state = self.client.session["fb_oauth_state"]["value"]
        leaky = MetaApiError(f"{USER_TOKEN} {SECRET}", code=190)
        with graph_patches(error=leaky), self.assertLogs("apps.social.meta", level=logging.INFO) as logs:
            response = self.client.get(reverse("social:facebook_callback"), {"code": "CODE-777", "state": state}, follow=True)
        text = response.content.decode() + "\n".join(logs.output)
        for secret in (USER_TOKEN, SECRET, "CODE-777"):
            self.assertNotIn(secret, text)

    def test_AC_16_graph_calls_never_put_credentials_in_urls(self):
        session = mock.Mock()
        session.request.side_effect = [
            FakeResponse({"access_token": USER_TOKEN}),
            FakeResponse({"access_token": USER_TOKEN}),
            FakeResponse({"data": [{"id": "1", "name": "A", "access_token": PAGE_TOKEN_1}]}),
            FakeResponse({"id": "1"}),
        ]
        client = GraphClient(app_id="123", app_secret=SECRET, config_id="456",
                             redirect_uri="http://localhost/cb", version="v27.0", session=session)
        client.extend_token(client.exchange_code("CODE-777"))
        client.list_pages(USER_TOKEN)
        client.get_page("1", PAGE_TOKEN_1)
        for call in session.request.call_args_list:
            url = call.args[1]
            query = str(call.kwargs.get("params") or "")
            for secret in (*SECRETS, "CODE-777"):
                self.assertNotIn(secret, url)
                self.assertNotIn(secret, query)

    def test_AC_16_network_errors_do_not_leak_the_request_secret(self):
        session = mock.Mock()
        session.request.side_effect = requests.ConnectionError(f"falha em {SECRET}")
        client = GraphClient(app_id="123", app_secret=SECRET, config_id="456",
                             redirect_uri="http://localhost/cb", version="v27.0", session=session)
        with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs, self.assertRaises(MetaApiError) as ctx:
            client.exchange_code("c")
        self.assertNotIn(SECRET, str(ctx.exception))
        self.assertNotIn(SECRET, "\n".join(logs.output))


@override_settings(**VALID_META_SETTINGS)
class AccessControlTests(TestCase):
    def test_AC_17_every_feature_route_requires_login_and_does_nothing_for_anonymous(self):
        account_url = lambda n: reverse(n, args=[1])  # noqa: E731
        routes = [
            ("post", reverse("social:facebook_connect")),
            ("get", reverse("social:facebook_callback") + "?code=x&state=y"),
            ("get", reverse("social:facebook_select")),
            ("post", reverse("social:facebook_select")),
            ("get", reverse("social:accounts")),
            ("post", account_url("social:account_check")),
            ("post", account_url("social:account_disconnect")),
        ]
        with graph_patches() as mocks:
            for method, url in routes:
                with self.subTest(url=url):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response["Location"].startswith(reverse("accounts:login")))
            for m in mocks:
                m.assert_not_called()
        self.assertEqual(SocialAccount.objects.count(), 0)
