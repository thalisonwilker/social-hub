from types import SimpleNamespace
from unittest import mock

from django.test import TestCase, override_settings

from apps.social.images import sanitize_image
from apps.social.models import PublicationTarget
from apps.social.services import publishing, threads_publish

from .evolution_helpers import EVOLUTION_SETTINGS, make_whatsapp_account
from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_evolution_publisher import evolution_mocks
from .test_threads_publisher import TEXT, Clock, threads_mocks
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status
SETTINGS = {**THREADS_SETTINGS, "PUBLISH_REQUEST_BUDGET_SECONDS": 150, "THREADS_IMAGE_WAIT_SECONDS": 60, "PUBLISH_BATCH_SIZE": 5}


@override_settings(**SETTINGS)
class BudgetTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.clock = Clock()

    def slow_uploads(self, seconds):
        """Cada upload do Facebook 'demora' `seconds` no relógio falso."""
        def side_effect(client, page_id, token, **kw):
            self.clock.t += seconds
            return {"photo_id": "p", "post_id": f"{page_id}_77"}

        self.publish.side_effect = side_effect

    def test_AC_17_does_not_start_a_target_with_less_than_40_seconds_left(self):
        """AC-17: restam 30 s → o próximo alvo não inicia e fica pending; log publish_budget_exhausted."""
        self.slow_uploads(120)
        pub = self.make_publication(self.make_accounts(3))
        with self.assertLogs("apps.social.meta", level="WARNING") as logs:
            result = publishing.send_pending(pub, clock=self.clock)
        self.assertEqual((result.attempted, result.published, result.remaining), (1, 1, 2))
        self.assertEqual(sorted(pub.targets.values_list("status", flat=True)), [S.PENDING, S.PENDING, S.PUBLISHED])
        self.assertIn("publish_budget_exhausted remaining=2", "\n".join(logs.output))

    def test_AC_17_exactly_40_seconds_left_still_starts_the_target(self):
        """AC-17: restam exatamente 40 s → inicia (o limite é 'menos de 40')."""
        self.slow_uploads(110)
        pub = self.make_publication(self.make_accounts(2))
        result = publishing.send_pending(pub, clock=self.clock)
        self.assertEqual((result.attempted, result.remaining), (2, 0))

    def test_AC_17_continue_sending_picks_up_the_pending_targets(self):
        """AC-17: 'Continuar envio' (nova chamada, orçamento novo) envia os que ficaram pending."""
        self.slow_uploads(120)
        pub = self.make_publication(self.make_accounts(3))
        publishing.send_pending(pub, clock=self.clock)
        self.clock.t = 0
        self.slow_uploads(10)
        result = publishing.send_pending(pub, clock=self.clock)
        self.assertEqual((result.attempted, result.published, result.remaining), (2, 2, 0))

    def test_AC_17_batch_size_remains_a_ceiling(self):
        """AC-17: PUBLISH_BATCH_SIZE continua limitando os alvos por requisição."""
        pub = self.make_publication(self.make_accounts(4))
        result = publishing.send_pending(pub, batch_size=2, clock=self.clock)
        self.assertEqual((result.attempted, result.remaining), (2, 2))

    def test_AC_17_fast_batches_are_not_affected(self):
        """AC-17: sem demora (relógio parado) o lote de 5 sai inteiro, como na 0003."""
        pub = self.make_publication(self.make_accounts(5))
        result = publishing.send_pending(pub, clock=self.clock)
        self.assertEqual((result.attempted, result.published, result.remaining), (5, 5, 0))

    def test_AC_18_image_wait_is_limited_by_the_remaining_budget(self):
        """AC-18: restam 50 s ao iniciar → espera = min(60, 50 − 25) = 25 s; esgotada vira failed (AC-14)."""
        threads = make_threads_account(self.alice, "900")
        pub = publishing.create_publication(self.alice, TEXT, sanitize_image(make_upload()), [threads])
        self.clock.t = 100  # 100 s já gastos no orçamento de 150 (iniciado em t=0 → restam 50)
        fake_time = SimpleNamespace(sleep=self.clock.sleep, monotonic=self.clock)
        started = self.clock.t
        with threads_mocks(statuses=("IN_PROGRESS",)) as api, mock.patch.object(threads_publish, "time", fake_time):
            publishing.send_pending(pub, clock=self._offset_clock(100))
        waited = self.clock.t - started
        self.assertGreaterEqual(waited, 25)
        self.assertLess(waited, 29)  # 25 s + no máximo um intervalo de 3 s
        target = pub.targets.get()
        self.assertEqual((target.status, target.error_message), (S.FAILED, publishing.MSG_THREADS_IMAGE_PENDING))
        api["publish_container"].assert_not_called()

    def test_AC_18_full_wait_when_the_budget_is_plentiful(self):
        """AC-18: com orçamento folgado a espera é a configurada (60 s)."""
        threads = make_threads_account(self.alice, "900")
        pub = publishing.create_publication(self.alice, TEXT, sanitize_image(make_upload()), [threads])
        fake_time = SimpleNamespace(sleep=self.clock.sleep, monotonic=self.clock)
        with threads_mocks(statuses=("IN_PROGRESS",)), mock.patch.object(threads_publish, "time", fake_time):
            publishing.send_pending(pub, clock=self.clock)
        self.assertGreaterEqual(self.clock.t, 60)
        self.assertLess(self.clock.t, 64)

    def test_AC_18_text_targets_keep_their_own_wait(self):
        """AC-18: container de texto segue usando THREADS_CONTAINER_WAIT_SECONDS (20 s), sem imagem."""
        threads = make_threads_account(self.alice, "900")
        pub = publishing.create_publication(self.alice, TEXT, None, [threads])
        fake_time = SimpleNamespace(sleep=self.clock.sleep, monotonic=self.clock)
        with threads_mocks(statuses=("IN_PROGRESS",)), mock.patch.object(threads_publish, "time", fake_time):
            publishing.send_pending(pub, clock=self.clock)
        self.assertGreaterEqual(self.clock.t, 20)
        self.assertLess(self.clock.t, 23)

    def _offset_clock(self, elapsed):
        """Relógio do orçamento: já 'passou' `elapsed` s desde o início da requisição (que começou em t=0)."""
        calls = {"n": 0}

        def clock():
            calls["n"] += 1
            return self.clock.t if calls["n"] > 1 else self.clock.t - elapsed

        return clock


@override_settings(**EVOLUTION_SETTINGS, PUBLISH_REQUEST_BUDGET_SECONDS=150, PUBLISH_BATCH_SIZE=5)
class WhatsAppBudgetTests(PublicationTestMixin, TestCase):
    """Orçamento de tempo com o WhatsApp (spec 0006, AC-13): timeout = min(config, restante − 25 s); < 40 s não inicia."""

    def setUp(self):
        super().setUp()
        self.clock = Clock()
        # nome que ordena DEPOIS da Página do Facebook ("Página 1"), para o Facebook ir primeiro
        self.wa = make_whatsapp_account(self.alice, "loja", name="Zeta Loja")

    def slow_facebook(self, seconds):
        def side_effect(client, page_id, token, **kw):
            self.clock.t += seconds
            return {"photo_id": "p", "post_id": f"{page_id}_77"}

        self.publish.side_effect = side_effect

    def pub(self, *, image=False, with_facebook=False):
        accounts = [self.wa] + (self.make_accounts(1) if with_facebook else [])
        image = image or with_facebook  # Página do Facebook exige imagem
        return publishing.create_publication(self.alice, TEXT, sanitize_image(make_upload()) if image else None, accounts)

    def timeout_used(self, api, kind=None):
        """Timeout da chamada de Status feita (texto ou imagem, o que foi chamado)."""
        called = [m for name, m in api.items() if name.startswith("send_status") and m.called]
        assert len(called) == 1, "esperava exatamente um tipo de Status enviado"
        return called[0].call_args.kwargs["timeout"]

    def test_AC_13_full_budget_uses_the_configured_timeout(self):
        """AC-13: orçamento intacto (150 s) → timeout = min(60, 150 − 25) = 60 s."""
        pub = self.pub()
        with evolution_mocks() as api:
            publishing.send_pending(pub, clock=self.clock)
        self.assertEqual(self.timeout_used(api), 60)

    @override_settings(EVOLUTION_TIMEOUT_SECONDS=30)
    def test_AC_13_a_smaller_configured_timeout_wins(self):
        """AC-13: EVOLUTION_TIMEOUT_SECONDS menor que o restante vale como está (30 s)."""
        pub = self.pub(image=True)
        with evolution_mocks() as api:
            publishing.send_pending(pub, clock=self.clock)
        self.assertEqual(self.timeout_used(api, "send_status_image"), 30)

    def test_AC_13_the_timeout_shrinks_with_the_remaining_budget(self):
        """AC-13: o Facebook gastou 100 s → restam 50 → timeout = min(60, 50 − 25) = 25 s."""
        self.slow_facebook(100)
        pub = self.pub(with_facebook=True)
        with evolution_mocks() as api:
            result = publishing.send_pending(pub, clock=self.clock)
        self.assertEqual((result.attempted, result.published), (2, 2))
        self.assertEqual(self.timeout_used(api), 25)

    def test_AC_13_exactly_40_seconds_left_still_starts_with_a_15_second_timeout(self):
        """AC-13: restam exatamente 40 s → inicia, com timeout = 40 − 25 = 15 s."""
        self.slow_facebook(110)
        pub = self.pub(with_facebook=True)
        with evolution_mocks() as api:
            publishing.send_pending(pub, clock=self.clock)
        self.assertEqual(self.timeout_used(api), 15)

    def test_AC_13_with_less_than_40_seconds_the_target_is_not_started(self):
        """AC-13: restam 30 s → o alvo do WhatsApp não inicia, fica `pending`, nenhuma chamada, log do orçamento."""
        self.slow_facebook(120)
        pub = self.pub(with_facebook=True)
        with evolution_mocks() as api, self.assertLogs("apps.social.meta", level="WARNING") as logs:
            result = publishing.send_pending(pub, clock=self.clock)
        self.assertEqual((result.attempted, result.published, result.remaining), (1, 1, 1))
        for mock_ in api.values():
            mock_.assert_not_called()
        wa_target = pub.targets.get(platform="whatsapp_status")
        self.assertEqual((wa_target.status, wa_target.attempts), (S.PENDING, 0))
        self.assertIn("publish_budget_exhausted remaining=1", "\n".join(logs.output))

    def test_AC_13_continue_sending_starts_the_pending_whatsapp_target_with_a_fresh_budget(self):
        """AC-13: "Continuar envio" (orçamento novo) publica o alvo que ficou `pending`, com o timeout cheio."""
        self.slow_facebook(120)
        pub = self.pub(with_facebook=True)
        with evolution_mocks():
            publishing.send_pending(pub, clock=self.clock)
        self.clock.t = 0
        with evolution_mocks() as api:
            result = publishing.send_pending(pub, clock=self.clock)
        self.assertEqual((result.attempted, result.published, result.remaining), (1, 1, 0))
        self.assertEqual(self.timeout_used(api), 60)

    def test_AC_13_state_probe_after_a_failure_is_short_and_fits_the_margin(self):
        """AC-13: a sondagem de estado depois de uma falha tem no máximo 10 s (cabe na folga de 25 s)."""
        from apps.social.services.evolution import EvolutionApiError

        pub = self.pub()
        with evolution_mocks(text=EvolutionApiError("x", code="rejected", status=400)) as api:
            publishing.send_pending(pub, clock=self.clock)
        self.assertLessEqual(api["connection_state"].call_args.kwargs["timeout"], 10)
        self.assertLessEqual(10, publishing.WAIT_SAFETY_MARGIN)
