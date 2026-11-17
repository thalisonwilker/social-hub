"""Segurança transversal da 0006 (AC-14, AC-16): Evolution FALSA no transporte (`requests.Session.request`),
com o cliente, as views e os serviços REAIS. Registra o que de fato seria enviado pela rede."""
import base64
import logging
from urllib.parse import urlparse

import requests
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from unittest import mock

from apps.social.models import Publication, PublicationTarget, SocialAccount

from .evolution_helpers import EVO_HOST, EVOLUTION_SETTINGS, make_whatsapp_account
from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_meta_client import FakeResponse

KEY = "CHAVE-SECRETA-DA-ALICE-9f3a"
KEY_BOB = "CHAVE-SECRETA-DO-BOB-77c1"
TEXT = "TEXTO-CONFIDENCIAL-DO-STATUS-42"
RAW_BODY = "CORPO-CRU-DA-EVOLUTION-xyz"
NEW = "social:post_new"
S = PublicationTarget.Status


class FakeEvolution:
    """Servidor falso: registra cada chamada (método, URL, headers, corpo) e responde conforme o cenário."""

    def __init__(self, *, state="open", send_status=201, send_payload=None, state_status=200):
        self.state, self.send_status, self.state_status = state, send_status, state_status
        self.send_payload = send_payload if send_payload is not None else {"key": {"id": "MSG-1"}}
        self.calls = []

    def handle(self, _session, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, "headers": kwargs.get("headers") or {}, "json": kwargs.get("json"), "kwargs": kwargs})
        if "/instance/connectionState/" in url:
            return FakeResponse({"instance": {"state": self.state}}, status=self.state_status)
        return FakeResponse(self.send_payload, status=self.send_status)

    def patch(self):
        return mock.patch.object(requests.Session, "request", autospec=True, side_effect=self.handle)

    @property
    def sent_bodies(self):
        return [c["json"] for c in self.calls if c["json"]]


@override_settings(**EVOLUTION_SETTINGS)
class EvolutionSecurityTests(PublicationTestMixin, TestCase):
    def register(self, instance="minha-loja", key=KEY, client=None):
        return (client or self.client).post(reverse("social:whatsapp_new"), {"instance_name": instance, "api_key": key}, follow=True)

    def do_publish(self, accounts, *, text=TEXT, image=True, client=None, **extra):
        data = {"text": text, "accounts": [str(a.pk) for a in accounts], **extra}
        if image:
            data["image"] = make_upload()
        return (client or self.client).post(reverse(NEW), data, follow=True)

    def all_pages(self, pub=None):
        urls = [reverse("social:accounts"), reverse(NEW), reverse("social:posts")]
        if pub:
            urls.append(reverse("social:post_detail", args=[pub.pk]))
        return {url: self.client.get(url).content.decode() for url in urls}

    # ---- AC-14: o que vai pela rede ----------------------------------------
    def test_AC_14_every_call_goes_to_the_configured_host_with_the_key_only_in_the_header(self):
        """AC-14: cadastro + publicação com imagem → só duas rotas conhecidas, host do servidor, sem query, chave só no header."""
        evo = FakeEvolution()
        with evo.patch():
            self.register()
            account = SocialAccount.objects.get()
            self.do_publish([account])
        self.assertEqual([c["method"] for c in evo.calls], ["GET", "POST"])
        for call in evo.calls:
            parsed = urlparse(call["url"])
            self.assertEqual((parsed.scheme, parsed.netloc), ("https", EVO_HOST))
            self.assertEqual((parsed.query, parsed.fragment, parsed.params), ("", "", ""))
            self.assertEqual(call["headers"], {"apikey": KEY})
            self.assertIsNone(call["kwargs"].get("params"))
            self.assertIsNone(call["kwargs"].get("data"))
        self.assertEqual(urlparse(evo.calls[0]["url"]).path, "/instance/connectionState/minha-loja")
        self.assertEqual(urlparse(evo.calls[1]["url"]).path, "/message/sendStatus/minha-loja")
        image_body = evo.sent_bodies[0]
        self.assertEqual((image_body["type"], image_body["caption"]), ("image", TEXT))
        encoded = image_body["content"]
        for call in evo.calls:
            for secret in (KEY, TEXT, encoded):
                self.assertNotIn(secret, call["url"])

    def test_AC_14_forged_host_headers_and_hostile_instance_names_never_change_the_destination(self):
        """AC-14: Host/X-Forwarded-Host forjados e nome de instância com URL não alteram o destino; nada hostil chega à rede."""
        evo = FakeEvolution()
        hostile = ["https://evil.example/x", "evil.example/..", "../../etc/passwd", "a/b", "a?x=1", "a#b", "a%2e%2e", "a b", "a\nb"]
        with evo.patch():
            for name in hostile:
                self.register(instance=name)
            self.assertEqual(evo.calls, [])
            self.assertEqual(SocialAccount.objects.count(), 0)
            self.register()
            account = SocialAccount.objects.get()
            self.client.post(
                reverse(NEW),
                {"text": TEXT, "accounts": [str(account.pk)], "image": make_upload()},
                HTTP_X_FORWARDED_HOST="evil.example",
                HTTP_ORIGIN="https://evil.example",
                HTTP_REFERER="https://evil.example/",
            )
        self.assertTrue(evo.calls)
        for call in evo.calls:
            self.assertEqual(urlparse(call["url"]).netloc, EVO_HOST)

    def test_AC_14_a_legacy_account_with_a_hostile_instance_name_never_reaches_the_network(self):
        """AC-14: mesmo uma conta gravada com nome fora do padrão (dado legado/manual) é recusada antes da rede."""
        bad = make_whatsapp_account(self.alice, "ok", key=KEY)
        SocialAccount.objects.filter(pk=bad.pk).update(external_id="../../admin")
        evo = FakeEvolution()
        with evo.patch():
            self.client.get(reverse(NEW))
            pub = Publication.objects.create(owner=self.alice, text=TEXT)
            target = PublicationTarget.objects.create(
                publication=pub, account=SocialAccount.objects.get(pk=bad.pk), page_external_id="../../admin",
                page_name="x", platform=SocialAccount.Platform.WHATSAPP_STATUS,
            )
            from apps.social.services import publishing

            result = publishing.send_pending(pub)
        self.assertEqual(evo.calls, [])
        self.assertEqual((result.published, result.failed), (0, 1))
        target.refresh_from_db()
        self.assertEqual(target.status, S.FAILED)

    # ---- AC-14: segredos em repouso, logs, HTML, mensagens -----------------------
    def test_AC_14_key_is_encrypted_at_rest_and_never_in_reprs(self):
        """AC-14: a chave não aparece em nenhum campo da conta, nem em str()/repr()."""
        evo = FakeEvolution()
        with evo.patch():
            self.register()
        account = SocialAccount.objects.get()
        values = [str(getattr(account, f.name)) for f in account._meta.concrete_fields]
        values += [str(account), repr(account), repr(account.__dict__.get("access_token_enc"))]
        for value in values:
            self.assertNotIn(KEY, value)
        self.assertEqual(account.get_token(), KEY)

    def test_AC_14_happy_path_leaks_nothing_in_logs_or_pages(self):
        """AC-14: no fluxo feliz, chave e base64 não aparecem em logs nem em qualquer tela; o texto só na própria publicação."""
        evo = FakeEvolution()
        with evo.patch(), self.assertLogs(level=logging.DEBUG) as logs:
            self.register()
            account = SocialAccount.objects.get()
            response = self.do_publish([account])
            self.client.post(reverse("social:account_check", args=[account.pk]), follow=True)
        pub = Publication.objects.get()
        encoded = evo.sent_bodies[0]["content"]
        output = "\n".join(logs.output)
        for secret in (KEY, TEXT, encoded):
            self.assertNotIn(secret, output)
        pages = self.all_pages(pub)
        for url, html in pages.items():
            for secret in (KEY, encoded):
                self.assertNotIn(secret, html, url)
        for url, html in list(pages.items())[:2]:  # contas e formulário: nem o texto
            self.assertNotIn(TEXT, html, url)
        self.assertNotIn(KEY, response.content.decode())

    def test_AC_14_evolution_error_bodies_never_leak_to_logs_pages_or_stored_messages(self):
        """AC-14: a Evolution responde erro com corpo cru (ecoando chave e texto); nada disso chega a log, tela ou banco."""
        evo = FakeEvolution(send_status=500, send_payload={"message": f"{RAW_BODY} {KEY} {TEXT}"})
        with evo.patch():
            self.register()
            account = SocialAccount.objects.get()
            with self.assertLogs(level=logging.DEBUG) as logs:
                response = self.do_publish([account])
                pub = Publication.objects.get()
                pages = self.all_pages(pub)
        output = "\n".join(logs.output)
        target = pub.targets.get()
        self.assertEqual(target.status, S.FAILED)
        for secret in (RAW_BODY, KEY):
            self.assertNotIn(secret, output)
            self.assertNotIn(secret, target.error_message)
            self.assertNotIn(secret, target.error_code)
            self.assertNotIn(secret, response.content.decode())
            for html in pages.values():
                self.assertNotIn(secret, html)
        self.assertNotIn(RAW_BODY, "".join(m.message for m in response.context["messages"]))

    def test_AC_14_registration_errors_never_echo_the_key_or_the_raw_body(self):
        """AC-14: cadastro recusado (chave inválida, 401, 500, fora de `open`) não devolve a chave nem o corpo cru."""
        scenarios = [
            FakeEvolution(state_status=401), FakeEvolution(state_status=500), FakeEvolution(state="close"), FakeEvolution(state_status=404),
        ]
        for evo in scenarios:
            with self.subTest(state=evo.state, status=evo.state_status), evo.patch():
                response = self.register()
                self.assertEqual(SocialAccount.objects.count(), 0)
                html = response.content.decode()
                self.assertNotIn(KEY, html)
                self.assertNotIn(KEY, str(response.context["form"].errors))

    # ---- AC-16: isolamento -------------------------------------------------------
    def test_AC_16_each_user_publishes_with_their_own_key_even_with_the_same_instance_name(self):
        """AC-16: dois usuários, mesmo nome de instância; cada publicação usa a chave do dono."""
        bob_client = Client()
        bob_client.force_login(self.bob)
        evo = FakeEvolution()
        with evo.patch():
            self.register("loja", KEY)
            self.register("loja", KEY_BOB, client=bob_client)
            mine = SocialAccount.objects.get(owner=self.alice)
            theirs = SocialAccount.objects.get(owner=self.bob)
            evo.calls.clear()
            self.do_publish([mine], image=False)
            self.do_publish([theirs], image=False, client=bob_client)
        self.assertEqual([c["headers"]["apikey"] for c in evo.calls], [KEY, KEY_BOB])

    def test_AC_16_a_user_cannot_publish_check_or_disconnect_with_another_users_account(self):
        """AC-16: com a conta de outro usuário, publicar é rejeitado e verificar/desconectar dão 404; nada vai à rede."""
        make_whatsapp_account(self.alice, "da-alice", key=KEY)  # sem conta própria o formulário nem abre
        theirs = make_whatsapp_account(self.bob, "do-bob", key=KEY_BOB)
        evo = FakeEvolution()
        with evo.patch():
            response = self.do_publish([theirs], image=False)
            self.assertContains(response, "Seleção de Página inválida")
            self.assertEqual(self.client.post(reverse("social:account_check", args=[theirs.pk])).status_code, 404)
            self.assertEqual(self.client.post(reverse("social:account_disconnect", args=[theirs.pk])).status_code, 404)
        self.assertEqual(evo.calls, [])
        self.assertEqual(Publication.objects.count(), 0)
        self.assertTrue(SocialAccount.objects.filter(pk=theirs.pk).exists())

    def test_AC_16_account_actions_do_not_accept_get_and_require_csrf_and_login(self):
        """AC-16: GET em verificar/desconectar → 405; POST sem CSRF → 403; sem login → redireciona; nada vai à rede."""
        account = make_whatsapp_account(self.alice, "loja", key=KEY)
        evo = FakeEvolution()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.alice)
        anonymous = Client()
        with evo.patch():
            for name in ("social:account_check", "social:account_disconnect"):
                url = reverse(name, args=[account.pk])
                self.assertEqual(self.client.get(url).status_code, 405)
                self.assertEqual(strict.post(url).status_code, 403)
                self.assertEqual(anonymous.post(url).status_code, 302)
            self.assertEqual(strict.post(reverse("social:whatsapp_new"), {"instance_name": "x", "api_key": KEY}).status_code, 403)
            self.assertEqual(anonymous.post(reverse("social:whatsapp_new"), {"instance_name": "x", "api_key": KEY}).status_code, 302)
        self.assertEqual(evo.calls, [])
        self.assertTrue(SocialAccount.objects.filter(pk=account.pk).exists())

    def test_AC_16_other_users_publications_and_targets_are_invisible(self):
        """AC-16: a publicação de WhatsApp de um usuário é 404 para outro (detalhe, envio e imagem)."""
        mine = make_whatsapp_account(self.alice, "loja", key=KEY)
        evo = FakeEvolution()
        with evo.patch():
            self.do_publish([mine])
        pub = Publication.objects.get()
        self.client.force_login(self.bob)
        evo2 = FakeEvolution()
        with evo2.patch():
            for url in (
                reverse("social:post_detail", args=[pub.pk]),
                reverse("social:post_image", args=[pub.pk]),
            ):
                self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(reverse("social:post_send", args=[pub.pk])).status_code, 404)
        self.assertEqual(evo2.calls, [])
