"""Classificação do erro de rede (spec 0007, AC-6): "nunca chegou ao servidor" (`network`, certo) ×
"enviei e a resposta não veio" (`timeout`/`interrupted`, incerto) — só a CHAMADA COM EFEITO marca `outcome_unknown`."""
import logging
from unittest import mock

import requests
from django.test import SimpleTestCase
from urllib3.exceptions import (
    MaxRetryError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
)

from apps.social.services import publishing
from apps.social.services.evolution import EvolutionApiError, EvolutionClient
from apps.social.services.meta import GraphClient, MetaApiError
from apps.social.services.threads import ThreadsClient
from apps.social.services.transport import classify_request_error

from .test_meta_client import FakeResponse

SECRET = "SEGREDO-NA-URL-xyz"
BASE = "https://evo.exemplo.host"


def never_reached():
    """Falha de conexão (DNS/recusada): o servidor nunca recebeu a requisição."""
    inner = NewConnectionError(None, f"Failed to establish a new connection {SECRET}")
    return requests.ConnectionError(MaxRetryError(None, f"/x?token={SECRET}", inner))


def mid_flight():
    """Conexão cortada depois de enviar: o servidor pode ter processado."""
    return requests.ConnectionError(ProtocolError("Connection aborted.", ConnectionResetError(f"reset {SECRET}")))


def read_timeout():
    return requests.ReadTimeout(f"Read timed out {SECRET}")


CASES = {
    "connect_timeout": (requests.ConnectTimeout("lento"), "network"),
    "dns_or_refused": (never_reached(), "network"),
    "ssl": (requests.exceptions.SSLError("tls"), "network"),
    "proxy": (requests.exceptions.ProxyError("proxy"), "network"),
    "invalid_url": (requests.exceptions.InvalidURL("url"), "network"),
    "read_timeout": (read_timeout(), "timeout"),
    "generic_timeout": (requests.Timeout("t"), "timeout"),
    "reset_mid_flight": (mid_flight(), "interrupted"),
    "plain_connection_error": (requests.ConnectionError("caiu"), "interrupted"),
    "chunked": (requests.exceptions.ChunkedEncodingError("cortou"), "interrupted"),
    "urllib3_read_timeout_wrapped": (requests.ConnectionError(MaxRetryError(None, "/x", ReadTimeoutError(None, "/x", "t"))), "interrupted"),
}


class ClassifyRequestErrorTests(SimpleTestCase):
    def test_AC_6_each_error_is_classified_as_never_reached_timeout_or_interrupted(self):
        """AC-6: conexão nunca estabelecida → `network`; leitura esgotada → `timeout`; cortada depois de enviar → `interrupted`."""
        for name, (exc, expected) in CASES.items():
            with self.subTest(name):
                self.assertEqual(classify_request_error(exc), expected)

    def test_AC_6_in_doubt_defaults_to_interrupted_never_to_a_certain_failure(self):
        """AC-6: conexão com erro sem detalhe não pode ser tratada como "nunca chegou" (evita reenviar às cegas)."""
        self.assertEqual(classify_request_error(requests.ConnectionError()), "interrupted")


def make_graph(*outcomes):
    session = mock.Mock()
    session.request.side_effect = list(outcomes)
    return GraphClient(app_id="1", app_secret="s", config_id="2", redirect_uri="http://x/cb", version="v27.0", session=session)


def make_threads(*outcomes):
    session = mock.Mock()
    session.request.side_effect = list(outcomes)
    return ThreadsClient(app_id="1", app_secret="s", redirect_uri="https://x/cb", version="v1.0", session=session)


def make_evolution(*outcomes):
    session = mock.Mock()
    session.request.side_effect = list(outcomes)
    return EvolutionClient(base_url=BASE, timeout=60, session=session)


def photo(client):
    return client.publish_photo("1", "tok", image=b"x", filename="a.jpg", content_type="image/jpeg", message="Olá")


class GraphOutcomeTests(SimpleTestCase):
    def test_AC_6_facebook_effect_call_with_response_lost_is_outcome_unknown(self):
        """AC-6: upload do Facebook com leitura esgotada / conexão cortada → `timeout`/`interrupted` e `outcome_unknown`."""
        for outcome, code in ((read_timeout(), "timeout"), (mid_flight(), "interrupted")):
            with self.subTest(code=code):
                with self.assertRaises(MetaApiError) as ctx:
                    photo(make_graph(outcome))
                self.assertEqual((ctx.exception.code, ctx.exception.outcome_unknown), (code, True))

    def test_AC_6_facebook_effect_call_that_never_reached_the_server_is_a_certain_failure(self):
        """AC-6: DNS/recusada/TLS no upload → `network` e NÃO é incerto."""
        for outcome in (never_reached(), requests.ConnectTimeout("t"), requests.exceptions.SSLError("tls")):
            with self.subTest(type(outcome).__name__):
                with self.assertRaises(MetaApiError) as ctx:
                    photo(make_graph(outcome))
                self.assertEqual((ctx.exception.code, ctx.exception.outcome_unknown), ("network", False))

    def test_AC_6_facebook_error_responses_are_certain_failures(self):
        """AC-6: resposta de erro da Meta (token, permissão, 5xx) → `failed`, nunca incerto."""
        for status, body in ((400, {"error": {"code": 200}}), (500, {"error": {"code": 1}}), (503, {})):
            with self.subTest(status=status):
                with self.assertRaises(MetaApiError) as ctx:
                    photo(make_graph(FakeResponse(body, status=status)))
                self.assertFalse(ctx.exception.outcome_unknown)

    def test_AC_6_facebook_invalid_body_after_the_server_accepted_is_outcome_unknown(self):
        """AC-6: 2xx com corpo inválido na chamada com efeito: a Meta aceitou, mas o Hub não sabe o id → incerto."""
        for response in (FakeResponse(None, json_error=True), FakeResponse(["lista"])):
            with self.subTest(type(response._payload).__name__):
                with self.assertRaises(MetaApiError) as ctx:
                    photo(make_graph(response))
                self.assertEqual((ctx.exception.code, ctx.exception.outcome_unknown), ("bad_response", True))

    def test_AC_6_facebook_success_without_post_id_is_outcome_unknown(self):
        """AC-6: 2xx sem `post_id`/`id` na chamada com efeito → incerto (provavelmente publicou)."""
        with self.assertRaises(MetaApiError) as ctx:
            photo(make_graph(FakeResponse({"foo": "bar"})))
        self.assertEqual((ctx.exception.code, ctx.exception.outcome_unknown), ("bad_response", True))

    def test_AC_6_facebook_non_effect_calls_are_never_outcome_unknown(self):
        """AC-6: chamadas que não criam post (ex.: ler a Página) com timeout NÃO são incertas."""
        with self.assertRaises(MetaApiError) as ctx:
            make_graph(read_timeout()).get_page("1", "tok")
        self.assertEqual((ctx.exception.code, ctx.exception.outcome_unknown), ("timeout", False))

    def test_AC_6_new_codes_map_to_the_generic_network_message(self):
        """AC-6: `timeout`/`interrupted` nos fluxos sem efeito usam a mesma mensagem amigável de comunicação."""
        for code in ("network", "timeout", "interrupted", "bad_response"):
            self.assertEqual(publishing.friendly_error(MetaApiError("x", code=code)), publishing.MSG_NETWORK)


class ThreadsOutcomeTests(SimpleTestCase):
    def test_AC_6_threads_publish_is_the_only_effect_call(self):
        """AC-6: `threads_publish` sem resposta → incerto; criar container, consultar status e permalink → NÃO."""
        with self.assertRaises(MetaApiError) as ctx:
            make_threads(read_timeout()).publish_container("900", "tok", "c-1")
        self.assertEqual((ctx.exception.code, ctx.exception.outcome_unknown), ("timeout", True))
        calls = {
            "create_text_container": lambda c: c.create_text_container("900", "tok", "t"),
            "create_image_container": lambda c: c.create_image_container("900", "tok", "t", "https://x/i.jpg"),
            "container_status": lambda c: c.container_status("c-1", "tok"),
            "get_permalink": lambda c: c.get_permalink("m-1", "tok"),
        }
        for name, call in calls.items():
            with self.subTest(name):
                with self.assertRaises(MetaApiError) as ctx:
                    call(make_threads(read_timeout()))
                self.assertEqual((ctx.exception.code, ctx.exception.outcome_unknown), ("timeout", False))

    def test_AC_6_threads_publish_matrix(self):
        """AC-6: `threads_publish`: cortada → incerto; nunca chegou → certo; erro da Meta → certo; 2xx sem id → incerto."""
        cases = [
            (mid_flight(), "interrupted", True),
            (never_reached(), "network", False),
            (FakeResponse({"error": {"code": 190}}, status=401), 190, False),
            (FakeResponse({}), "bad_response", True),
        ]
        for outcome, code, unknown in cases:
            with self.subTest(code=code):
                with self.assertRaises(MetaApiError) as ctx:
                    make_threads(outcome).publish_container("900", "tok", "c-1")
                self.assertEqual((ctx.exception.code, ctx.exception.outcome_unknown), (code, unknown))


class EvolutionOutcomeTests(SimpleTestCase):
    def send(self, outcome, image=False):
        client = make_evolution(outcome)
        return client.send_status_image("loja", "k", b"img", "t") if image else client.send_status_text("loja", "k", "t")

    def test_AC_6_whatsapp_send_status_with_response_lost_is_outcome_unknown(self):
        """AC-6: `sendStatus` (texto e imagem) com leitura esgotada / conexão cortada → incerto."""
        for image in (False, True):
            for outcome, code in ((read_timeout(), "timeout"), (mid_flight(), "interrupted")):
                with self.subTest(image=image, code=code):
                    with self.assertRaises(EvolutionApiError) as ctx:
                        self.send(outcome, image)
                    self.assertEqual((ctx.exception.code, ctx.exception.outcome_unknown), (code, True))

    def test_AC_6_whatsapp_never_reached_and_error_responses_are_certain_failures(self):
        """AC-6: DNS/recusada/TLS → `network`; 4xx/5xx com resposta → certo; nada disso é incerto."""
        cases = [(never_reached(), "network"), (requests.ConnectTimeout("t"), "network"),
                 (FakeResponse({"m": "x"}, status=400), "rejected"), (FakeResponse({"m": "x"}, status=500), "server"),
                 (FakeResponse({}, status=401), "auth"), (FakeResponse({}, status=429), "rate_limit")]
        for outcome, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(EvolutionApiError) as ctx:
                    self.send(outcome)
                self.assertEqual((ctx.exception.code, ctx.exception.outcome_unknown), (code, False))

    def test_AC_6_whatsapp_invalid_body_after_a_2xx_is_outcome_unknown(self):
        """AC-6: 2xx com corpo inválido em `sendStatus`: a Evolution aceitou → incerto."""
        for response in (FakeResponse(None, json_error=True), FakeResponse(["x"])):
            with self.subTest(type(response._payload).__name__):
                with self.assertRaises(EvolutionApiError) as ctx:
                    self.send(response)
                self.assertEqual((ctx.exception.code, ctx.exception.outcome_unknown), ("bad_response", True))

    def test_AC_6_whatsapp_connection_state_is_never_outcome_unknown(self):
        """AC-6: consultar o estado (sem efeito) com timeout não é incerto."""
        with self.assertRaises(EvolutionApiError) as ctx:
            make_evolution(read_timeout()).connection_state("loja", "k")
        self.assertEqual((ctx.exception.code, ctx.exception.outcome_unknown), ("timeout", False))


class NoSecretsTests(SimpleTestCase):
    def test_AC_6_classification_logs_only_codes_and_never_the_exception_text(self):
        """AC-6: o log traz só rótulo e código; o texto da exceção (que costuma ter URL/token) nunca vai ao log nem à mensagem."""
        for outcome in (read_timeout(), mid_flight(), never_reached()):
            for make, call in (
                (make_graph, lambda c: photo(c)),
                (make_threads, lambda c: c.publish_container("900", "tok", "c-1")),
                (make_evolution, lambda c: c.send_status_text("loja", "k", "t")),
            ):
                with self.subTest(outcome=type(outcome).__name__, client=make.__name__):
                    with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs, self.assertRaises(Exception) as ctx:
                        call(make(outcome))
                    for text in ("\n".join(logs.output), str(ctx.exception)):
                        self.assertNotIn(SECRET, text)


class RealSocketTests(SimpleTestCase):
    """AC-6: a classificação depende de detalhes internos do urllib3; aqui com sockets REAIS em loopback (sem rede externa)."""

    @staticmethod
    def serve(handler):
        import socket
        import threading

        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)

        def run():
            try:
                conn, _ = server.accept()
                handler(conn)
                conn.close()
            except OSError:
                pass
            finally:
                server.close()

        threading.Thread(target=run, daemon=True).start()
        return server.getsockname()[1]

    @staticmethod
    def kind(call):
        try:
            call()
        except requests.RequestException as exc:
            return classify_request_error(exc)
        return "ok"

    def test_AC_6_connection_refused_never_reached_the_server(self):
        """AC-6: porta fechada → `network` (certo)."""
        import socket

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()  # ninguém escuta nessa porta
        self.assertEqual(self.kind(lambda: requests.post(f"http://127.0.0.1:{port}/x", data=b"x", timeout=3)), "network")

    def test_AC_6_server_that_never_answers_is_a_read_timeout(self):
        """AC-6: o servidor lê o pedido e não responde → `timeout` (incerto)."""
        import time

        port = self.serve(lambda conn: (conn.recv(65536), time.sleep(2)))
        self.assertEqual(self.kind(lambda: requests.post(f"http://127.0.0.1:{port}/x", data=b"x", timeout=0.5)), "timeout")

    def test_AC_6_server_that_closes_after_reading_is_interrupted(self):
        """AC-6: o servidor lê o pedido e fecha a conexão → `interrupted` (incerto)."""
        port = self.serve(lambda conn: conn.recv(65536))
        self.assertEqual(self.kind(lambda: requests.post(f"http://127.0.0.1:{port}/x", data=b"x", timeout=3)), "interrupted")

    def test_AC_6_response_cut_in_the_middle_is_interrupted(self):
        """AC-6: resposta cortada no meio do corpo → `interrupted` (incerto)."""
        port = self.serve(lambda conn: (conn.recv(65536), conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n{")))
        self.assertEqual(self.kind(lambda: requests.post(f"http://127.0.0.1:{port}/x", data=b"x", timeout=3)), "interrupted")

    def test_AC_6_tls_handshake_failure_never_sent_the_request(self):
        """AC-6: TLS contra um servidor que fala HTTP puro → `network` (a requisição nunca foi enviada)."""
        port = self.serve(lambda conn: (conn.recv(65536), conn.sendall(b"HTTP/1.1 400 Bad\r\n\r\n")))
        self.assertEqual(self.kind(lambda: requests.post(f"https://127.0.0.1:{port}/x", data=b"x", timeout=3)), "network")
