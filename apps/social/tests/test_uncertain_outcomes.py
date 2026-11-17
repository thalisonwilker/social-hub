"""Resultado incerto por plataforma (spec 0007, AC-6) e envio na requisição sem recuperação automática (AC-2)."""
import logging
from unittest import mock

from django.test import TestCase, override_settings

from apps.social.images import sanitize_image
from apps.social.models import PublicationTarget, SocialAccount
from apps.social.services import publishing
from apps.social.services.evolution import EvolutionApiError
from apps.social.services.meta import GraphClient, MetaApiError

from .evolution_helpers import EVOLUTION_SETTINGS, make_whatsapp_account
from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_evolution_publisher import evolution_mocks
from .test_threads_publisher import threads_mocks
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status
UNCERTAIN_MSG = publishing.MSG_UNCERTAIN
SECRET = "SEGREDO-NO-TEXTO-DA-EXCECAO"


def meta_unknown(code="timeout"):
    return MetaApiError(f"falha {SECRET}", code=code, outcome_unknown=True)


def evo_unknown(code="timeout"):
    return EvolutionApiError(f"falha {SECRET}", code=code, outcome_unknown=True)


@override_settings(**{**THREADS_SETTINGS, **EVOLUTION_SETTINGS})
class UncertainOutcomeTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.page = self.make_accounts(1)[0]
        self.profile = make_threads_account(self.alice, "900", username="maria")
        self.wa = make_whatsapp_account(self.alice, "loja", key="chave-da-loja")

    def make_pub(self, accounts, *, image=True):
        return publishing.create_publication(self.alice, "Texto confidencial", sanitize_image(make_upload()) if image else None, accounts)

    def only(self, pub):
        return pub.targets.get()

    def assertUncertain(self, target, code):
        target.refresh_from_db()
        self.assertEqual((target.status, target.error_code, target.error_message), (S.UNCERTAIN, code, UNCERTAIN_MSG))
        self.assertTrue(target.is_resolvable)

    # ---- Facebook ----------------------------------------------------------
    def test_AC_6_facebook_upload_without_response_becomes_uncertain(self):
        """AC-6: upload do Facebook com resposta perdida (`timeout`/`interrupted`) → Incerto, conta intacta, log só com o motivo."""
        for code in ("timeout", "interrupted"):
            with self.subTest(code=code):
                self.publish.side_effect = meta_unknown(code)
                pub = self.make_pub([self.page])
                with self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
                    result = publishing.send_pending(pub)
                self.assertEqual((result.published, result.failed, result.uncertain), (0, 0, 1))
                self.assertUncertain(self.only(pub), code)
                self.page.refresh_from_db()
                self.assertEqual(self.page.status, SocialAccount.Status.ACTIVE)
                self.assertIn(f"target_uncertain reason={code}", "\n".join(logs.output))
                self.assertNotIn(SECRET, "\n".join(logs.output))

    def test_AC_6_facebook_certain_failures_stay_failed(self):
        """AC-6: DNS/recusada (`network`, nunca chegou) e resposta de erro da Meta continuam `failed`."""
        for error in (MetaApiError("x", code="network"), MetaApiError("x", code=200, status=403), MetaApiError("x", code=1, status=500)):
            with self.subTest(code=error.code):
                self.publish.side_effect = error
                pub = self.make_pub([self.page])
                result = publishing.send_pending(pub)
                self.assertEqual((result.failed, result.uncertain), (1, 0))
                self.assertEqual(self.only(pub).status, S.FAILED)

    # ---- Threads -----------------------------------------------------------
    def test_AC_6_threads_publish_without_response_becomes_uncertain_and_keeps_the_container(self):
        """AC-6: `threads_publish` com resposta perdida → Incerto; o container gravado é mantido."""
        for image in (False, True):
            with self.subTest(image=image):
                pub = self.make_pub([self.profile], image=image)
                with threads_mocks(publish_container={"side_effect": meta_unknown("interrupted")}) as api:
                    result = publishing.send_pending(pub)
                self.assertEqual((result.failed, result.uncertain), (0, 1))
                target = self.only(pub)
                self.assertUncertain(target, "interrupted")
                self.assertNotEqual(target.external_container_id, "")
                api["publish_container"].assert_called_once()
                self.profile.refresh_from_db()
                self.assertEqual(self.profile.status, SocialAccount.Status.ACTIVE)
                SocialAccount.objects.filter(pk=self.profile.pk).update()  # sem efeito colateral
                PublicationTarget.objects.all().delete()

    def test_AC_6_threads_container_steps_never_make_the_target_uncertain(self):
        """AC-6: falhas ao criar o container ou consultar o status (nada publicado) continuam `failed`."""
        failing = {
            "create_text_container": {"side_effect": MetaApiError("x", code="timeout")},
        }
        pub = self.make_pub([self.profile], image=False)
        with threads_mocks(**failing):
            result = publishing.send_pending(pub)
        self.assertEqual((result.failed, result.uncertain), (1, 0))
        self.assertEqual(self.only(pub).status, S.FAILED)

    def test_AC_6_threads_certain_publish_failures_stay_failed(self):
        """AC-6: `threads_publish` que nunca chegou ou com erro da Meta (token) → `failed`."""
        for error in (MetaApiError("x", code="network"), MetaApiError("x", code=4, status=429)):
            with self.subTest(code=error.code):
                pub = self.make_pub([self.profile], image=False)
                with threads_mocks(publish_container={"side_effect": error}):
                    result = publishing.send_pending(pub)
                self.assertEqual((result.failed, result.uncertain), (1, 0))
                PublicationTarget.objects.all().delete()

    # ---- WhatsApp ----------------------------------------------------------
    def test_AC_6_whatsapp_send_status_without_response_becomes_uncertain(self):
        """AC-6: `sendStatus` (texto e imagem) com resposta perdida → Incerto; não sonda o estado, não mexe na conta."""
        for image in (False, True):
            for code in ("timeout", "interrupted"):
                with self.subTest(image=image, code=code):
                    pub = self.make_pub([self.wa], image=image)
                    with evolution_mocks(text=evo_unknown(code), image=evo_unknown(code)) as api, \
                            self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
                        result = publishing.send_pending(pub)
                    self.assertEqual((result.published, result.failed, result.uncertain), (0, 0, 1))
                    self.assertUncertain(self.only(pub), code)
                    api["connection_state"].assert_not_called()
                    self.wa.refresh_from_db()
                    self.assertEqual(self.wa.status, SocialAccount.Status.ACTIVE)
                    self.assertNotIn(SECRET, "\n".join(logs.output))
                    PublicationTarget.objects.all().delete()

    def test_AC_6_whatsapp_certain_failures_stay_failed(self):
        """AC-6: `network` (nunca chegou), recusa, 5xx e chave recusada continuam `failed`."""
        for code, status in (("network", None), ("rejected", 400), ("server", 500), ("auth", 401)):
            with self.subTest(code=code):
                pub = self.make_pub([self.wa], image=False)
                SocialAccount.objects.filter(pk=self.wa.pk).update(status=SocialAccount.Status.ACTIVE)
                with evolution_mocks(text=EvolutionApiError("x", code=code, status=status)):
                    result = publishing.send_pending(pub)
                self.assertEqual((result.failed, result.uncertain), (1, 0))
                PublicationTarget.objects.all().delete()

    # ---- regras comuns -----------------------------------------------------
    def test_AC_6_an_uncertain_target_is_never_resent_by_send_pending(self):
        """AC-6/AC-2: `send_pending` não reenvia alvo Incerto (nem o reivindica); só o usuário resolve."""
        pub = self.make_pub([self.page])
        self.publish.side_effect = meta_unknown()
        publishing.send_pending(pub)
        self.publish.reset_mock()
        self.publish.side_effect = None
        result = publishing.send_pending(pub)
        self.assertEqual((result.attempted, result.uncertain), (0, 0))
        self.publish.assert_not_called()
        self.assertEqual(self.only(pub).status, S.UNCERTAIN)

    def test_AC_6_other_targets_of_the_same_publication_keep_going(self):
        """AC-6: um alvo Incerto não impede os demais (publicação mista)."""
        pub = self.make_pub([self.page, self.profile, self.wa])
        with threads_mocks(), evolution_mocks(image=evo_unknown("timeout")):
            result = publishing.send_pending(pub)
        by_platform = {t.platform: t.status for t in pub.targets.all()}
        self.assertEqual(by_platform, {"facebook_page": S.PUBLISHED, "threads": S.PUBLISHED, "whatsapp_status": S.UNCERTAIN})
        self.assertEqual((result.published, result.uncertain), (2, 1))
        self.assertEqual(pub.status, "uncertain")

    def test_AC_2_failed_targets_are_requeued_atomically_and_sent_in_inline_mode(self):
        """AC-2: no modo inline "Tentar novamente" reenfileira `failed` (`failed → pending`) e envia na requisição."""
        pub = self.make_pub([self.page])
        self.publish.side_effect = MetaApiError("x", code=1, status=500)
        publishing.send_pending(pub)
        self.assertEqual(self.only(pub).status, S.FAILED)
        self.publish.side_effect = lambda client, page_id, token, **kw: {"photo_id": "p", "post_id": f"{page_id}_77"}
        result = publishing.send_pending(pub)
        self.assertEqual((result.attempted, result.published), (1, 1))
        self.assertEqual(self.only(pub).attempts, 2)

    def test_AC_2_report_counts_uncertain_targets(self):
        """AC-2: o resumo do lote conta os Incertos separadamente (BatchResult.uncertain)."""
        pub = self.make_pub([self.page])
        self.publish.side_effect = meta_unknown()
        self.assertEqual(publishing.send_pending(pub).uncertain, 1)


@override_settings(**{**THREADS_SETTINGS, **EVOLUTION_SETTINGS})
class UncertainBatchMessageTests(PublicationTestMixin, TestCase):
    def post_pub(self, accounts):
        from django.urls import reverse

        data = {"text": "Olá", "accounts": [str(a.pk) for a in accounts], "image": make_upload()}
        return self.client.post(reverse("social:post_new"), data, follow=True)

    def test_AC_2_inline_batch_message_reports_uncertain_targets(self):
        """AC-2: no modo inline o resumo diz "N incerta(s)" e manda conferir; nunca "Publicado em 0 Páginas"."""
        page = self.make_accounts(1)[0]
        self.publish.side_effect = meta_unknown()
        response = self.post_pub([page])
        self.assertContains(response, "0 publicada(s) e 1 incerta(s)")
        self.assertContains(response, "Confira na plataforma")
        self.assertNotContains(response, "Publicado em 0")

    def test_AC_2_inline_batch_message_with_failed_and_uncertain(self):
        """AC-2: com falha e incerto juntos, o resumo traz os três números."""
        pages = self.make_accounts(2)
        calls = iter([MetaApiError("x", code=1, status=500), meta_unknown()])

        def side_effect(client, page_id, token, **kw):
            raise next(calls)

        self.publish.side_effect = side_effect
        response = self.post_pub(pages)
        self.assertContains(response, "0 publicada(s), 1 com falha e 1 incerta(s)")
