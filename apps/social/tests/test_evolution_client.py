import base64
import logging
from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings

from apps.social.services.evolution import EvolutionApiError, EvolutionClient

from .helpers import KEY
from .test_meta_client import FakeResponse

BASE = "https://evo.exemplo.host"
INSTANCE_KEY = "chave-da-instancia-SECRETA-123"
TEXT = "Texto confidencial do Status do WhatsApp"
IMAGE = b"\xff\xd8\xff\xe0conteudo-binario-da-imagem\x00\x01\x02"
ENCODED = base64.b64encode(IMAGE).decode("ascii")


def make_client(*responses, timeout=60):
    session = mock.Mock()
    session.request.side_effect = list(responses)
    return EvolutionClient(base_url=BASE, timeout=timeout, session=session), session


def last(session):
    call = session.request.call_args_list[-1]
    return call.args, call.kwargs


class EvolutionClientConfigTests(SimpleTestCase):
    @override_settings(EVOLUTION_API_URL="https://evo.exemplo.host/manager/", EVOLUTION_TIMEOUT_SECONDS=45, META_TOKEN_ENCRYPTION_KEY=KEY)
    def test_AC_14_from_settings_uses_only_the_configured_origin_and_timeout(self):
        """AC-14: o host vem só da configuração do servidor (origem HTTPS); o timeout também."""
        client = EvolutionClient.from_settings()
        self.assertEqual(client.base_url, BASE)
        self.assertEqual(client.timeout, 45)

    @override_settings(EVOLUTION_API_URL="")
    def test_AC_14_from_settings_without_configuration_raises_not_configured(self):
        """AC-14: sem URL válida não há cliente (nenhum host alternativo é aceito)."""
        with self.assertRaises(EvolutionApiError) as ctx:
            EvolutionClient.from_settings()
        self.assertEqual(ctx.exception.code, "not_configured")


class EvolutionSendStatusTests(SimpleTestCase):
    def test_AC_8_text_status_is_one_post_to_the_instance_with_all_contacts(self):
        """AC-8: Status de texto = um POST em /message/sendStatus/{instância}, header apikey, audiência todos os contatos."""
        client, session = make_client(FakeResponse({"key": {"remoteJid": "status@broadcast", "id": "MSG-1"}}, status=201))
        message_id = client.send_status_text("minha-instancia", INSTANCE_KEY, TEXT)
        self.assertEqual(message_id, "MSG-1")
        self.assertEqual(session.request.call_count, 1)
        (method, url), kwargs = last(session)
        self.assertEqual((method, url), ("POST", f"{BASE}/message/sendStatus/minha-instancia"))
        self.assertEqual(kwargs["headers"]["apikey"], INSTANCE_KEY)
        body = kwargs["json"]
        self.assertEqual(body["type"], "text")
        self.assertEqual(body["content"], TEXT)
        self.assertIs(body["allContacts"], True)
        self.assertNotIn("statusJidList", body)
        self.assertIsNone(kwargs.get("params"))

    def test_AC_9_image_status_sends_base64_with_the_text_as_caption(self):
        """AC-9: Status de imagem = um POST com o arquivo em base64 (sem URL pública) e o texto como legenda."""
        client, session = make_client(FakeResponse({"key": {"id": "MSG-2"}}))
        self.assertEqual(client.send_status_image("minha-instancia", INSTANCE_KEY, IMAGE, TEXT), "MSG-2")
        (method, url), kwargs = last(session)
        self.assertEqual((method, url), ("POST", f"{BASE}/message/sendStatus/minha-instancia"))
        body = kwargs["json"]
        self.assertEqual(body["type"], "image")
        self.assertEqual(body["content"], ENCODED)
        self.assertEqual(base64.b64decode(body["content"]), IMAGE)
        self.assertEqual(body["caption"], TEXT)
        self.assertIs(body["allContacts"], True)
        self.assertNotIn("http", body["content"])

    def test_AC_8_response_without_message_id_is_still_success(self):
        """AC-8: o id da mensagem é opcional; sem ele devolve string vazia."""
        client, _ = make_client(FakeResponse({"status": "PENDING"}))
        self.assertEqual(client.send_status_text("minha-instancia", INSTANCE_KEY, TEXT), "")

    def test_AC_12_timeout_argument_overrides_the_default(self):
        """AC-12: o timeout por chamada é repassado (o publicador o limita pelo orçamento restante)."""
        client, session = make_client(FakeResponse({}), FakeResponse({}), timeout=60)
        client.send_status_text("i", INSTANCE_KEY, TEXT)
        self.assertEqual(last(session)[1]["timeout"], 60)
        client.send_status_text("i", INSTANCE_KEY, TEXT, timeout=12.5)
        self.assertEqual(last(session)[1]["timeout"], 12.5)


class EvolutionConnectionStateTests(SimpleTestCase):
    def test_AC_14_connection_state_is_a_get_with_the_instance_key_in_the_header(self):
        """AC-14: o estado é um GET; a chave vai só no header e nunca na URL."""
        client, session = make_client(FakeResponse({"instance": {"instanceName": "minha-instancia", "state": "open"}}))
        self.assertEqual(client.connection_state("minha-instancia", INSTANCE_KEY), "open")
        (method, url), kwargs = last(session)
        self.assertEqual((method, url), ("GET", f"{BASE}/instance/connectionState/minha-instancia"))
        self.assertEqual(kwargs["headers"]["apikey"], INSTANCE_KEY)
        self.assertNotIn(INSTANCE_KEY, url)
        self.assertIsNone(kwargs.get("params"))

    def test_AC_14_connection_state_accepts_flat_and_nested_responses_and_normalises_case(self):
        """AC-14: o estado vem aninhado (`instance.state`) ou plano (`state`); comparado em minúsculas."""
        for payload in ({"state": "OPEN"}, {"instance": {"state": "Open"}}):
            with self.subTest(payload=payload):
                client, _ = make_client(FakeResponse(payload))
                self.assertEqual(client.connection_state("i", INSTANCE_KEY), "open")

    def test_AC_12_connection_state_without_state_is_a_bad_response(self):
        """AC-12: resposta sem estado → erro `bad_response`."""
        client, _ = make_client(FakeResponse({"instance": {}}))
        with self.assertRaises(EvolutionApiError) as ctx:
            client.connection_state("i", INSTANCE_KEY)
        self.assertEqual(ctx.exception.code, "bad_response")


class EvolutionErrorMappingTests(SimpleTestCase):
    CASES = {
        401: "auth", 403: "auth", 404: "not_found", 429: "rate_limit",
        400: "rejected", 422: "rejected", 413: "rejected", 500: "server", 502: "server", 503: "server",
    }

    def test_AC_12_http_statuses_map_to_short_codes(self):
        """AC-12: cada status HTTP vira um código curto (auth, not_found, rate_limit, rejected, server)."""
        for status, code in self.CASES.items():
            with self.subTest(status=status):
                client, _ = make_client(FakeResponse({"message": "texto cru da Evolution com a chave " + INSTANCE_KEY}, status=status))
                with self.assertRaises(EvolutionApiError) as ctx:
                    client.send_status_text("i", INSTANCE_KEY, TEXT)
                self.assertEqual((ctx.exception.code, ctx.exception.status), (code, status))
                self.assertNotIn(INSTANCE_KEY, str(ctx.exception))
                self.assertNotIn("cru", str(ctx.exception))

    def test_AC_12_network_timeout_and_bad_body_have_their_own_codes(self):
        """AC-12: timeout → `timeout`; falha de rede → `network`; corpo não-JSON ou não-objeto → `bad_response`."""
        cases = [
            (requests.Timeout("lento"), "timeout"),
            (requests.ConnectionError("caiu"), "network"),
            (FakeResponse(None, json_error=True), "bad_response"),
            (FakeResponse(["lista"]), "bad_response"),
        ]
        for outcome, code in cases:
            with self.subTest(code=code):
                client, _ = make_client(outcome)
                with self.assertRaises(EvolutionApiError) as ctx:
                    client.send_status_text("i", INSTANCE_KEY, TEXT)
                self.assertEqual(ctx.exception.code, code)

    def test_AC_12_http_error_inside_a_2xx_json_is_not_treated_as_success(self):
        """AC-12: status 2xx com objeto de erro explícito (`error`) também falha como `rejected`."""
        client, _ = make_client(FakeResponse({"error": "Bad Request"}, status=200))
        with self.assertRaises(EvolutionApiError) as ctx:
            client.send_status_text("i", INSTANCE_KEY, TEXT)
        self.assertEqual(ctx.exception.code, "rejected")


class EvolutionSecurityTests(SimpleTestCase):
    HOSTILE = ["", "a/b", "..", "a?b", "a#b", "a%2Fb", "a b", "a\nb", "x" * 65, "a.b"]

    def test_AC_14_hostile_instance_names_never_reach_the_network(self):
        """AC-14: nome fora do padrão é recusado no cliente, sem nenhuma chamada."""
        for name in self.HOSTILE:
            with self.subTest(name=name):
                client, session = make_client()
                for call in (
                    lambda: client.send_status_text(name, INSTANCE_KEY, TEXT),
                    lambda: client.send_status_image(name, INSTANCE_KEY, IMAGE, TEXT),
                    lambda: client.connection_state(name, INSTANCE_KEY),
                ):
                    with self.assertRaises(EvolutionApiError) as ctx:
                        call()
                    self.assertEqual(ctx.exception.code, "invalid_instance")
                session.request.assert_not_called()

    def test_AC_14_url_never_contains_the_key_text_or_image(self):
        """AC-14: a URL chamada é só host fixo + rota; chave, texto e imagem ficam no header/corpo."""
        client, session = make_client(FakeResponse({}), FakeResponse({}))
        client.send_status_text("i", INSTANCE_KEY, TEXT)
        client.send_status_image("i", INSTANCE_KEY, IMAGE, TEXT)
        for call in session.request.call_args_list:
            url = call.args[1]
            self.assertTrue(url.startswith(BASE + "/"))
            for secret in (INSTANCE_KEY, TEXT, ENCODED):
                self.assertNotIn(secret, url)

    def test_AC_14_failures_log_only_endpoint_status_and_code(self):
        """AC-14: o log de erro não traz chave, texto, base64, nome da instância nem corpo da resposta."""
        for outcome in (FakeResponse({"message": "corpo cru"}, status=500), requests.ConnectionError("caiu"), FakeResponse(None, json_error=True)):
            with self.subTest(outcome=str(outcome)):
                client, _ = make_client(outcome)
                with self.assertLogs("apps.social.meta", level="WARNING") as logs:
                    with self.assertRaises(EvolutionApiError):
                        client.send_status_image("minha-instancia", INSTANCE_KEY, IMAGE, TEXT)
                output = "\n".join(logs.output)
                self.assertIn("evolution_error", output)
                for secret in (INSTANCE_KEY, TEXT, ENCODED, "minha-instancia", "corpo cru", "evo.exemplo.host"):
                    self.assertNotIn(secret, output)

    def test_AC_14_success_does_not_log_anything_sensitive(self):
        """AC-14: o sucesso não registra chave, texto nem base64."""
        client, _ = make_client(FakeResponse({"key": {"id": "MSG-9"}}))
        with self.assertLogs("apps.social.meta", level=logging.DEBUG) as logs:
            logging.getLogger("apps.social.meta").debug("sentinela")
            client.send_status_image("minha-instancia", INSTANCE_KEY, IMAGE, TEXT)
        output = "\n".join(logs.output)
        for secret in (INSTANCE_KEY, TEXT, ENCODED):
            self.assertNotIn(secret, output)
