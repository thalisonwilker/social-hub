"""Segurança transversal da publicação em segundo plano (spec 0007, AC-17 e AC-20).

Plataformas FALSAS no transporte (`requests.Session.request`), com clientes, views, worker e serviços REAIS: registra o que de fato
sairia pela rede e confere que nenhum segredo, texto, base64 ou URL assinada vaza em log, JSON, HTML ou mensagem."""
import logging
import re
from urllib.parse import urlparse

import requests
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from unittest import mock

from apps.social.images import sanitize_image
from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services import publishing
from apps.social.services.worker import Worker

from .evolution_helpers import EVO_HOST, EVOLUTION_SETTINGS, make_whatsapp_account
from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_meta_client import FakeResponse
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status
TEXT = "TEXTO-CONFIDENCIAL-DA-PUBLICACAO-77"
FB_TOKEN = "FB-TOKEN-DA-PAGINA-SECRETO-111"
THREADS_TOKEN = "THREADS-TOKEN-SECRETO-222"
WA_KEY = "CHAVE-DA-INSTANCIA-SECRETA-333"
EXC_SECRET = "SEGREDO-DENTRO-DA-EXCECAO-444"
ALLOWED_HOSTS = {"graph.facebook.com", "graph.threads.com", EVO_HOST}


class FakePlatforms:
    """Servidor falso das três plataformas. `fail_effect`: plataformas cuja chamada com efeito perde a resposta (timeout de leitura)."""

    def __init__(self, fail_effect=()):
        self.fail_effect = set(fail_effect)
        self.calls = []

    def handle(self, _session, method, url, **kwargs):
        parsed = urlparse(url)
        self.calls.append({"method": method, "url": url, "host": parsed.netloc, "path": parsed.path, **kwargs})
        host, path = parsed.netloc, parsed.path
        if host == "graph.facebook.com":
            if path.endswith("/photos"):
                self._maybe_timeout("facebook")
                return FakeResponse({"id": "ph-1", "post_id": "1_77"})
            return FakeResponse({})
        if host == "graph.threads.com":
            if path.endswith("/threads_publish"):
                self._maybe_timeout("threads")
                return FakeResponse({"id": "m-1"})
            if path.endswith("/threads") and method == "POST":
                return FakeResponse({"id": "c-1"})
            fields = (kwargs.get("params") or {}).get("fields", "")
            if "permalink" in fields:
                return FakeResponse({"permalink": "https://www.threads.com/@maria/post/abc"})
            if "status" in fields:
                return FakeResponse({"status": "FINISHED", "error_message": ""})
            return FakeResponse({})
        if host == EVO_HOST and path.startswith("/message/sendStatus/"):
            self._maybe_timeout("evolution")
            return FakeResponse({"key": {"id": "MSG-1"}}, status=201)
        if host == EVO_HOST:
            return FakeResponse({"instance": {"state": "open"}})
        raise AssertionError(f"chamada a host inesperado: {host}")

    def _maybe_timeout(self, name):
        if name in self.fail_effect:
            raise requests.ReadTimeout(f"Read timed out {EXC_SECRET}")

    def patch(self):
        return mock.patch.object(requests.Session, "request", autospec=True, side_effect=self.handle)

    def calls_to(self, host):
        return [c for c in self.calls if c["host"] == host]


@override_settings(**{**THREADS_SETTINGS, **EVOLUTION_SETTINGS}, PUBLISH_MODE="worker")
class BackgroundSecurityTests(PublicationTestMixin, TestCase):
    mock_publish_photo = False  # o GraphClient real roda; só o transporte é falso

    def setUp(self):
        super().setUp()
        self.page = self.make_accounts(1)[0]
        self.page.set_token(FB_TOKEN)
        self.page.save()
        self.profile = make_threads_account(self.alice, "900", username="maria", token=THREADS_TOKEN)
        self.wa = make_whatsapp_account(self.alice, "loja", key=WA_KEY)

    # --- utilitários -----------------------------------------------------------
    def publish(self, client=None, accounts=None, text=TEXT):
        accounts = accounts or [self.page, self.profile, self.wa]
        data = {"text": text, "accounts": [str(a.pk) for a in accounts], "image": make_upload()}
        return (client or self.client).post(reverse("social:post_new"), data, follow=True)

    def drain(self, cycles=6):
        worker = Worker(pid=1)
        return [worker.run_once() for _ in range(cycles)]

    def pages(self, pub):
        urls = {
            "detalhe": reverse("social:post_detail", args=[pub.pk]),
            "historico": reverse("social:posts"),
            "contas": reverse("social:accounts"),
            "nova": reverse("social:post_new"),
        }
        return {name: self.client.get(url).content.decode() for name, url in urls.items()}

    def state(self, pub):
        return self.client.get(reverse("social:post_state", args=[pub.pk]))

    def assertNoLeak(self, haystack, secrets, where):
        for secret in secrets:
            self.assertNotIn(secret, haystack, f"{secret!r} vazou em {where}")

    # ---- AC-17: fluxo feliz ponta a ponta ---------------------------------------
    def test_AC_17_happy_path_sends_only_where_expected_and_leaks_nothing(self):
        """AC-17: Facebook + Threads + WhatsApp pela fila: só os três hosts, cada segredo só onde o cliente o usa; nada em log, JSON, HTML ou mensagens."""
        fake = FakePlatforms()
        with fake.patch(), self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger("apps.social.meta").debug("sentinela")
            response = self.publish()
            pub = Publication.objects.get()
            self.drain()
            pages = self.pages(pub)
            state = self.state(pub)
        self.assertEqual({t.status for t in pub.targets.all()}, {S.PUBLISHED})
        self.assertEqual({c["host"] for c in fake.calls}, ALLOWED_HOSTS)

        # cada segredo só aparece onde o cliente da sua plataforma o coloca
        for call in fake.calls_to("graph.facebook.com"):
            self.assertEqual(call["headers"].get("Authorization"), f"Bearer {FB_TOKEN}")
            self.assertNotIn(THREADS_TOKEN, repr(call))
            self.assertNotIn(WA_KEY, repr(call))
        for call in fake.calls_to("graph.threads.com"):
            self.assertNotIn(THREADS_TOKEN, call["url"])  # nunca na URL
            self.assertNotIn(FB_TOKEN, repr(call))
            self.assertNotIn(WA_KEY, repr(call))
        for call in fake.calls_to(EVO_HOST):
            self.assertEqual(call["headers"], {"apikey": WA_KEY})
            self.assertNotIn(WA_KEY, call["url"])
            self.assertNotIn(FB_TOKEN, repr(call["json"] or ""))

        # segredos de terceiros e dados que NUNCA podem sair do servidor
        evolution_body = next(c["json"] for c in fake.calls_to(EVO_HOST) if c["json"])
        base64_payload = evolution_body["content"].split(",", 1)[1]
        signed_image_url = next(
            c["data"]["image_url"] for c in fake.calls_to("graph.threads.com") if (c.get("data") or {}).get("image_url")
        )
        signed_token = re.search(r"[?&]t=([^&]+)", signed_image_url).group(1)
        secrets = [FB_TOKEN, THREADS_TOKEN, WA_KEY, base64_payload, signed_token, signed_image_url]

        output = "\n".join(logs.output)
        self.assertNoLeak(output, secrets + [TEXT], "logs")
        self.assertNoLeak(state.content.decode(), secrets + [TEXT], "JSON de estado")
        messages_text = "".join(m.message for m in response.context["messages"])
        self.assertNoLeak(messages_text, secrets + [TEXT], "mensagens")
        for name, html in pages.items():
            self.assertNoLeak(html, secrets, f"HTML ({name})")
        self.assertNoLeak(pages["contas"] + pages["nova"], [TEXT], "HTML sem publicação")

    # ---- AC-17: incerteza ponta a ponta ---------------------------------------------
    def test_AC_17_uncertain_flow_never_exposes_exception_text_or_secrets(self):
        """AC-17: a resposta perdida nas três plataformas vira Incerto; o texto da exceção (com segredo) nunca chega a log, JSON, HTML ou mensagem."""
        fake = FakePlatforms(fail_effect={"facebook", "threads", "evolution"})
        with fake.patch(), self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger("apps.social.meta").debug("sentinela")
            self.publish()
            pub = Publication.objects.get()
            self.drain()
            pages = self.pages(pub)
            state = self.state(pub)
        self.assertEqual({t.status for t in pub.targets.all()}, {S.UNCERTAIN})
        self.assertEqual({t.error_message for t in pub.targets.all()}, {publishing.MSG_UNCERTAIN})
        self.assertEqual({t.error_code for t in pub.targets.all()}, {"timeout"})
        secrets = [FB_TOKEN, THREADS_TOKEN, WA_KEY, EXC_SECRET, "Read timed out"]
        self.assertNoLeak("\n".join(logs.output), secrets + [TEXT], "logs")
        self.assertNoLeak(state.content.decode(), secrets + [TEXT], "JSON de estado")
        for name, html in pages.items():
            self.assertNoLeak(html, secrets, f"HTML ({name})")
        data = state.json()
        self.assertEqual((data["status"], data["done"]), ("uncertain", True))

    def test_AC_17_resolving_and_resending_leaks_nothing_and_never_resends_on_its_own(self):
        """AC-17: Já foi publicado/Reenviar no fluxo real: nada vaza, e só o Reenviar chama a plataforma de novo (uma vez)."""
        fake = FakePlatforms(fail_effect={"facebook", "evolution"})
        with fake.patch(), self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger("apps.social.meta").debug("sentinela")
            self.publish(accounts=[self.page, self.wa])
            pub = Publication.objects.get()
            self.drain()
            facebook, whatsapp = pub.targets.order_by("platform")
            assert (facebook.platform, whatsapp.platform) == ("facebook_page", "whatsapp_status")
            self.drain()  # nada reenviado sozinho: continua tudo Incerto
            calls_before = len(fake.calls)
            self.client.post(reverse("social:target_resolve", args=[pub.pk, facebook.pk]), {"acao": "publicado"})
            self.assertEqual(len(fake.calls), calls_before, "marcar como publicado não chama plataforma")
            fake.fail_effect.clear()
            self.client.post(reverse("social:target_resolve", args=[pub.pk, whatsapp.pk]), {"acao": "reenviar"})
            self.assertEqual(len(fake.calls), calls_before, "reenviar só enfileira; quem envia é o worker")
            self.drain()
        self.assertEqual({t.platform: t.status for t in pub.targets.all()}, {"facebook_page": S.PUBLISHED, "whatsapp_status": S.PUBLISHED})
        self.assertEqual(len(fake.calls_to(EVO_HOST)), calls_before - len([c for c in fake.calls[:calls_before] if c["host"] != EVO_HOST]) + 1)
        self.assertNoLeak("\n".join(logs.output), [FB_TOKEN, WA_KEY, EXC_SECRET, TEXT], "logs")
        self.assertNoLeak("\n".join(self.pages(pub).values()), [FB_TOKEN, WA_KEY, EXC_SECRET], "HTML")

    # ---- AC-17: isolamento entre usuários ------------------------------------------
    def test_AC_17_each_users_queued_targets_use_their_own_credentials_and_stay_private(self):
        """AC-17: dois usuários, mesma instância: o worker usa a chave do dono de cada alvo; um não vê nem resolve o do outro."""
        bob = self.bob
        bob_client = Client()
        bob_client.force_login(bob)
        bob_key = "CHAVE-DO-BOB-SECRETA-555"
        bob_wa = make_whatsapp_account(bob, "loja", key=bob_key)
        fake = FakePlatforms()
        with fake.patch():
            self.publish(accounts=[self.wa])
            bob_response = bob_client.post(
                reverse("social:post_new"), {"text": "Texto do Bob", "accounts": [str(bob_wa.pk)], "image": make_upload()}, follow=True
            )
            self.assertContains(bob_response, "Publicação enfileirada")
            self.drain()
        keys = [c["headers"]["apikey"] for c in fake.calls_to(EVO_HOST) if c["path"].startswith("/message/sendStatus/")]
        self.assertEqual(keys, [WA_KEY, bob_key])  # FIFO: cada alvo com a chave do seu dono
        alices, bobs = Publication.objects.get(owner=self.alice), Publication.objects.get(owner=bob)
        target = alices.targets.get()
        PublicationTarget.objects.filter(pk=target.pk).update(status=S.UNCERTAIN)
        self.assertEqual(bob_client.get(reverse("social:post_state", args=[alices.pk])).status_code, 404)
        self.assertEqual(bob_client.get(reverse("social:post_detail", args=[alices.pk])).status_code, 404)
        self.assertEqual(
            bob_client.post(reverse("social:target_resolve", args=[alices.pk, target.pk]), {"acao": "publicado"}).status_code, 404
        )
        self.assertEqual(bob_client.post(reverse("social:post_send", args=[alices.pk])).status_code, 404)
        self.assertEqual(PublicationTarget.objects.get(pk=target.pk).status, S.UNCERTAIN)
        self.assertNotIn("Texto do Bob", self.client.get(reverse("social:posts")).content.decode())
        self.assertNotIn(TEXT, bob_client.get(reverse("social:posts")).content.decode())
        self.assertEqual(bobs.targets.get().status, S.PUBLISHED)

    # ---- AC-17: erro inesperado no worker -------------------------------------------
    def test_AC_17_an_unexpected_exception_with_a_secret_never_reaches_logs_pages_or_json(self):
        """AC-17: um bug no despacho com segredo na mensagem da exceção: log só com o tipo; alvo Incerto; nada em HTML/JSON."""
        fake = FakePlatforms()
        with fake.patch(), self.assertLogs(level=logging.DEBUG) as logs, \
                mock.patch.object(publishing.ClientPool, "evolution", side_effect=RuntimeError(f"falha {WA_KEY} {EXC_SECRET}")):
            logging.getLogger("apps.social.meta").debug("sentinela")
            self.publish(accounts=[self.wa])
            pub = Publication.objects.get()
            self.drain(2)
            pages, state = self.pages(pub), self.state(pub)
        target = pub.targets.get()
        self.assertEqual((target.status, target.error_code), (S.UNCERTAIN, "worker_error"))
        output = "\n".join(logs.output)
        self.assertIn("RuntimeError", output)
        for secret in (WA_KEY, EXC_SECRET):
            self.assertNoLeak(output, [secret], "logs")
            self.assertNoLeak(state.content.decode(), [secret], "JSON")
            for name, html in pages.items():
                self.assertNoLeak(html, [secret], f"HTML ({name})")

    # ---- AC-17: JSON de estado mínimo em todo o ciclo ---------------------------------
    def test_AC_17_state_json_stays_minimal_in_every_phase_of_the_lifecycle(self):
        """AC-17: na fila, enviando, publicado, falhou e incerto o JSON tem sempre as mesmas cinco chaves e nenhum dado sensível."""
        fake = FakePlatforms()
        with fake.patch():
            self.publish(accounts=[self.page, self.profile, self.wa])
        pub = Publication.objects.get()
        first, second, third = list(pub.targets.order_by("id"))
        phases = [
            {},
            {first.pk: S.SENDING},
            {first.pk: S.PUBLISHED, second.pk: S.FAILED, third.pk: S.UNCERTAIN},
        ]
        for phase in phases:
            for pk, status in phase.items():
                PublicationTarget.objects.filter(pk=pk).update(
                    status=status, error_message="Mensagem com detalhe interno", error_code="x", permalink="https://exemplo/post"
                )
            raw = self.state(pub).content.decode()
            data = self.state(pub).json()
            self.assertEqual(set(data), {"status", "counts", "targets", "worker", "done"})
            for leak in (TEXT, FB_TOKEN, THREADS_TOKEN, WA_KEY, "Mensagem com detalhe interno", "https://", "maria", "loja"):
                self.assertNotIn(leak, raw)

    # ---- AC-20: compatibilidade ------------------------------------------------------
    @override_settings(PUBLISH_MODE="inline")
    def test_AC_20_inline_mode_still_publishes_in_the_request_with_the_same_security_properties(self):
        """AC-20: modo inline (regressão das 0003–0006): envia na requisição, mesmo transporte falso, sem vazamentos em log."""
        fake = FakePlatforms()
        with fake.patch(), self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger("apps.social.meta").debug("sentinela")
            self.publish()
        pub = Publication.objects.get()
        self.assertEqual({t.status for t in pub.targets.all()}, {S.PUBLISHED})
        self.assertEqual({c["host"] for c in fake.calls}, ALLOWED_HOSTS)
        self.assertNoLeak("\n".join(logs.output), [FB_TOKEN, THREADS_TOKEN, WA_KEY, TEXT], "logs (inline)")
