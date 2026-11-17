import logging
from contextlib import contextmanager
from unittest import mock

from django.test import TestCase, override_settings

from apps.social.images import sanitize_image
from apps.social.models import PublicationTarget, SocialAccount
from apps.social.services import publishing
from apps.social.services.evolution import EvolutionApiError, EvolutionClient

from .evolution_helpers import EVOLUTION_SETTINGS, make_whatsapp_account
from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin

S = PublicationTarget.Status
KEY = "chave-da-loja"
TEXT = "Promoção de hoje ☀️ confidencial"
REAUTH = "Reconecte o número na Evolution."
COMM = "Falha de comunicação com a Evolution."
RATE = "Limite de requisições. Tente mais tarde."
REJECTED = "A Evolution recusou este conteúdo."


@contextmanager
def evolution_mocks(*, text=None, image=None, state="open", state_error=None):
    """Patches do EvolutionClient (sem rede). `text`/`image`/`state_error`: exceção (EvolutionApiError) ou None."""
    specs = {
        "send_status_text": {"return_value": "MSG-T", "side_effect": text},
        "send_status_image": {"return_value": "MSG-I", "side_effect": image},
        "connection_state": {"return_value": state, "side_effect": state_error},
    }
    patchers, mocks = [], {}
    for name, kwargs in specs.items():
        patcher = mock.patch.object(EvolutionClient, name, **kwargs)
        mocks[name] = patcher.start()
        patchers.append(patcher)
    try:
        yield mocks
    finally:
        for patcher in patchers:
            patcher.stop()


def err(code, status=None, *, unknown=False):
    return EvolutionApiError("erro", code=code, status=status, outcome_unknown=unknown)


@override_settings(**EVOLUTION_SETTINGS)
class WhatsAppPublisherTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.wa = make_whatsapp_account(self.alice, "loja", name="Loja do centro", key=KEY)

    def make_pub(self, *, image=False, accounts=None, text=TEXT):
        accounts = accounts if accounts is not None else [self.wa]
        return publishing.create_publication(self.alice, text, sanitize_image(make_upload()) if image else None, accounts)

    def target(self, pub):
        return pub.targets.get()

    # ---- AC-8 ------------------------------------------------------------
    def test_AC_8_text_publication_sends_one_text_status_and_publishes_the_target(self):
        """AC-8: sem imagem → uma chamada de Status de texto com a chave da conta; alvo `published`, sem link, id guardado."""
        pub = self.make_pub()
        with evolution_mocks() as api, self.assertLogs("apps.social.meta", level=logging.INFO) as logs:
            result = publishing.send_pending(pub)
        self.assertEqual((result.attempted, result.published, result.failed), (1, 1, 0))
        api["send_status_text"].assert_called_once()
        self.assertEqual(api["send_status_text"].call_args.args, ("loja", KEY, TEXT))
        api["send_status_image"].assert_not_called()
        self.publish.assert_not_called()  # nada do Facebook
        target = self.target(pub)
        self.assertEqual(target.status, S.PUBLISHED)
        self.assertEqual((target.external_post_id, target.permalink, target.error_message, target.error_code), ("MSG-T", "", "", ""))
        self.assertIsNotNone(target.published_at)
        output = "\n".join(logs.output)
        self.assertIn("evolution_status_sent", output)
        for secret in (KEY, TEXT):
            self.assertNotIn(secret, output)

    def test_AC_8_response_without_id_still_publishes(self):
        """AC-8: o id da mensagem é opcional."""
        pub = self.make_pub()
        with evolution_mocks() as api:
            api["send_status_text"].return_value = ""
            publishing.send_pending(pub)
        target = self.target(pub)
        self.assertEqual((target.status, target.external_post_id), (S.PUBLISHED, ""))

    # ---- AC-9 ------------------------------------------------------------
    def test_AC_9_image_publication_sends_the_sanitized_file_with_the_text_as_caption(self):
        """AC-9: com imagem → uma chamada de Status de imagem com os bytes do arquivo sanitizado e o texto como legenda."""
        pub = self.make_pub(image=True)
        with pub.image.open("rb") as fh:
            expected = fh.read()
        with evolution_mocks() as api:
            publishing.send_pending(pub)
        api["send_status_image"].assert_called_once()
        args = api["send_status_image"].call_args.args
        self.assertEqual((args[0], args[1], args[2], args[3]), ("loja", KEY, expected, TEXT))
        self.assertEqual(api["send_status_image"].call_args.kwargs["content_type"], "image/jpeg")
        api["send_status_text"].assert_not_called()
        target = self.target(pub)
        self.assertEqual((target.status, target.external_post_id), (S.PUBLISHED, "MSG-I"))

    def test_AC_9_missing_image_file_fails_without_calling_the_evolution(self):
        """AC-9: arquivo da imagem ausente → `failed` com a mensagem de imagem indisponível e nenhuma chamada."""
        pub = self.make_pub(image=True)
        pub.image.storage.delete(pub.image.name)
        with evolution_mocks() as api:
            result = publishing.send_pending(pub)
        self.assertEqual((result.published, result.failed), (0, 1))
        for mock_ in api.values():
            mock_.assert_not_called()
        target = self.target(pub)
        self.assertEqual((target.status, target.error_message, target.error_code), (S.FAILED, publishing.MSG_IMAGE_MISSING, "image_missing"))

    # ---- AC-11 (matriz de envio) ---------------------------------------------
    def test_AC_11_account_already_in_reauth_fails_without_calling_the_evolution(self):
        """AC-11: conta já em Reconexão necessária → `failed` "Reconecte o número na Evolution", nenhuma chamada."""
        pub = self.make_pub()
        SocialAccount.objects.filter(pk=self.wa.pk).update(status=SocialAccount.Status.NEEDS_REAUTH)
        with evolution_mocks() as api:
            publishing.send_pending(pub)
        for mock_ in api.values():
            mock_.assert_not_called()
        target = self.target(pub)
        self.assertEqual((target.status, target.error_message, target.error_code), (S.FAILED, REAUTH, "reauth"))

    def test_AC_11_auth_and_not_found_mark_the_account_for_reconnection(self):
        """AC-11: 401/403 e instância inexistente → `failed` "Reconecte…" e a conta vira Reconexão necessária."""
        for code in ("auth", "not_found"):
            with self.subTest(code=code):
                SocialAccount.objects.filter(pk=self.wa.pk).update(status=SocialAccount.Status.ACTIVE)
                pub = self.make_pub()
                with evolution_mocks(text=err(code, 401)) as api:
                    publishing.send_pending(pub)
                api["connection_state"].assert_not_called()
                target = self.target(pub)
                self.assertEqual((target.status, target.error_message, target.error_code), (S.FAILED, REAUTH, code))
                self.wa.refresh_from_db()
                self.assertEqual(self.wa.status, SocialAccount.Status.NEEDS_REAUTH)
                self.assertNotEqual(self.wa.last_error, "")

    def test_AC_11_state_not_open_after_a_failed_send_marks_the_account_for_reconnection(self):
        """AC-11: falha de envio (recusa/5xx/resposta inválida) com a instância fora de `open` → Reconexão necessária."""
        for code in ("rejected", "server", "bad_response"):
            with self.subTest(code=code):
                SocialAccount.objects.filter(pk=self.wa.pk).update(status=SocialAccount.Status.ACTIVE)
                pub = self.make_pub()
                with evolution_mocks(text=err(code, 500), state="close") as api:
                    publishing.send_pending(pub)
                api["connection_state"].assert_called_once()
                self.assertEqual(api["connection_state"].call_args.args[:2], ("loja", KEY))
                target = self.target(pub)
                self.assertEqual((target.status, target.error_message), (S.FAILED, REAUTH))
                self.wa.refresh_from_db()
                self.assertEqual(self.wa.status, SocialAccount.Status.NEEDS_REAUTH)

    def test_AC_11_retry_only_works_after_the_account_is_active_again(self):
        """AC-11: com a conta em reconexão o reenvio falha sem chamar a Evolution; ativa de novo, publica."""
        pub = self.make_pub()
        with evolution_mocks(text=err("auth", 401)):
            publishing.send_pending(pub)
        with evolution_mocks() as api:
            publishing.send_pending(pub)
            api["send_status_text"].assert_not_called()
        self.assertEqual(self.target(pub).status, S.FAILED)
        SocialAccount.objects.filter(pk=self.wa.pk).update(status=SocialAccount.Status.ACTIVE)
        with evolution_mocks() as api:
            result = publishing.send_pending(pub)
        self.assertEqual((result.published, result.failed), (1, 0))
        self.assertEqual(self.target(pub).status, S.PUBLISHED)

    # ---- AC-12 -----------------------------------------------------------
    def test_AC_12_other_failures_are_retryable_with_friendly_messages_and_keep_the_account(self):
        """AC-12: timeout/rede/5xx/resposta inválida, 429 e recusa → `failed` com mensagem do caso; conta intacta; código guardado."""
        cases = [
            ("timeout", COMM), ("network", COMM), ("server", COMM), ("bad_response", COMM),
            ("rate_limit", RATE), ("rejected", REJECTED),
        ]
        for code, message in cases:
            with self.subTest(code=code):
                pub = self.make_pub()
                with evolution_mocks(text=err(code, 500)):  # a sondagem de estado devolve `open`
                    publishing.send_pending(pub)
                target = self.target(pub)
                self.assertEqual((target.status, target.error_message, target.error_code), (S.FAILED, message, code))
                self.assertTrue(target.is_retryable)
                self.wa.refresh_from_db()
                self.assertEqual(self.wa.status, SocialAccount.Status.ACTIVE)

    def test_AC_12_state_probe_is_skipped_for_timeouts_and_network_errors(self):
        """AC-12: timeout/rede/limite não sondam o estado (a Evolution está inacessível ou limitando)."""
        for code in ("timeout", "network", "rate_limit"):
            with self.subTest(code=code):
                with evolution_mocks(text=err(code)) as api:
                    publishing.send_pending(self.make_pub())
                api["connection_state"].assert_not_called()

    def test_AC_12_a_failing_state_probe_falls_back_to_the_generic_message(self):
        """AC-12: se a própria sondagem de estado falha, vale a mensagem do erro original e a conta não muda."""
        pub = self.make_pub()
        with evolution_mocks(text=err("rejected", 400), state_error=err("timeout")):
            publishing.send_pending(pub)
        self.assertEqual(self.target(pub).error_message, REJECTED)
        self.wa.refresh_from_db()
        self.assertEqual(self.wa.status, SocialAccount.Status.ACTIVE)

    def test_AC_12_try_again_resends_failed_targets_and_publishes(self):
        """AC-12: "Tentar novamente" reenvia o alvo `failed` e ele publica quando a Evolution volta."""
        pub = self.make_pub()
        with evolution_mocks(text=err("timeout")):
            publishing.send_pending(pub)
        self.assertEqual(self.target(pub).status, S.FAILED)
        with evolution_mocks() as api:
            result = publishing.send_pending(pub)
        self.assertEqual((result.attempted, result.published), (1, 1))
        api["send_status_text"].assert_called_once()
        self.assertEqual(self.target(pub).attempts, 2)

    def test_AC_12_published_target_is_never_resent(self):
        """AC-12: alvo `published` nunca é reenviado."""
        pub = self.make_pub()
        with evolution_mocks():
            publishing.send_pending(pub)
        with evolution_mocks() as api:
            result = publishing.send_pending(pub)
        self.assertEqual(result.attempted, 0)
        api["send_status_text"].assert_not_called()

    def test_AC_12_not_configured_fails_without_calling_the_evolution(self):
        """AC-12: sem EVOLUTION_API_URL o alvo falha com "Integração com o WhatsApp não configurada." e nada é chamado."""
        pub = self.make_pub()
        with override_settings(EVOLUTION_API_URL=""), evolution_mocks() as api:
            publishing.send_pending(pub)
        for mock_ in api.values():
            mock_.assert_not_called()
        target = self.target(pub)
        self.assertEqual((target.status, target.error_message, target.error_code), (S.FAILED, publishing.MSG_WHATSAPP_NOT_CONFIGURED, "not_configured"))

    def test_AC_12_unreadable_key_fails_with_the_credentials_message(self):
        """AC-12: chave que não descriptografa → `failed` (mensagem de credenciais), sem chamar a Evolution."""
        pub = self.make_pub()
        SocialAccount.objects.filter(pk=self.wa.pk).update(access_token_enc="lixo")
        with evolution_mocks() as api:
            publishing.send_pending(pub)
        api["send_status_text"].assert_not_called()
        target = self.target(pub)
        self.assertEqual((target.status, target.error_message, target.error_code), (S.FAILED, publishing.MSG_CREDENTIALS_WHATSAPP, "crypto"))

    def test_AC_12_failure_logs_carry_only_codes(self):
        """AC-12: o log de falha não traz chave, texto nem a mensagem crua da exceção."""
        pub = self.make_pub()
        with evolution_mocks(text=EvolutionApiError("texto cru " + KEY, code="rejected", status=400)), \
                self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
            publishing.send_pending(pub)
        output = "\n".join(logs.output)
        self.assertIn("publish_failed", output)
        for secret in (KEY, TEXT, "texto cru"):
            self.assertNotIn(secret, output)
        self.assertNotIn(KEY, self.target(pub).error_message)
