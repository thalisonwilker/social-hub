"""Worker de envio (spec 0007): AC-3 (FIFO, um por vez, sem orçamento), AC-7 (partida), AC-8 (vencido) e AC-15 (laço, sinais, comandos)."""
import io
import logging
import signal
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.social.images import sanitize_image
from apps.social.models import Publication, PublicationTarget, SocialAccount, WorkerHeartbeat
from apps.social.services import publishing, threads_publish
from apps.social.services.worker import Worker

from .evolution_helpers import EVOLUTION_SETTINGS, make_whatsapp_account
from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_evolution_publisher import evolution_mocks
from .test_threads_publisher import Clock, threads_mocks
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status
SECRET = "SEGREDO-DO-TEXTO-OU-DO-ERRO"


@override_settings(**{**THREADS_SETTINGS, **EVOLUTION_SETTINGS}, PUBLISH_MODE="worker", WORKER_POLL_SECONDS=2)
class WorkerBase(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.page = self.make_accounts(1)[0]
        self.profile = make_threads_account(self.alice, "900", username="maria")
        self.wa = make_whatsapp_account(self.alice, "loja", key="chave-da-loja")
        self.worker = Worker(pid=4242, sleep=lambda seconds: self.sleeps.append(seconds))
        self.sleeps = []

    def pub(self, accounts, *, text="Texto confidencial", image=True):
        return publishing.create_publication(self.alice, text, sanitize_image(make_upload()) if image else None, accounts)

    def statuses(self, pub):
        return {t.platform: t.status for t in pub.targets.all()}


class FifoTests(WorkerBase):
    # ---- AC-3 --------------------------------------------------------------
    def test_AC_3_oldest_pending_target_goes_first_and_one_per_cycle(self):
        """AC-3: cada ciclo envia UM alvo, do mais antigo (id) para o mais novo, de qualquer publicação."""
        first = self.pub([self.page])
        second = self.pub([self.page])
        third = self.pub([self.page])
        order = []
        self.publish.side_effect = lambda client, page_id, token, **kw: (order.append("graph"), {"photo_id": "p", "post_id": f"{page_id}_{len(order)}"})[1]
        self.assertEqual(self.worker.run_once(), S.PUBLISHED)
        self.assertEqual([p.targets.get().status for p in (first, second, third)], [S.PUBLISHED, S.PENDING, S.PENDING])
        self.assertEqual(self.worker.run_once(), S.PUBLISHED)
        self.assertEqual([p.targets.get().status for p in (first, second, third)], [S.PUBLISHED, S.PUBLISHED, S.PENDING])
        self.assertEqual(self.worker.run_once(), S.PUBLISHED)
        self.assertIsNone(self.worker.run_once())  # fila vazia
        self.assertEqual(self.publish.call_count, 3)

    def test_AC_3_each_platform_goes_through_its_own_dispatch_with_the_same_result_as_before(self):
        """AC-3: Facebook, Threads e WhatsApp saem pelo despacho da plataforma, com o mesmo resultado das 0003–0006."""
        pub = self.pub([self.page, self.profile, self.wa])
        with threads_mocks() as threads, evolution_mocks() as evo:
            results = [self.worker.run_once() for _ in range(4)]
        self.assertEqual(results[:3], [S.PUBLISHED] * 3)
        self.assertIsNone(results[3])
        self.assertEqual(self.publish.call_count, 1)
        threads["create_image_container"].assert_called_once()
        evo["send_status_image"].assert_called_once()
        self.assertEqual(set(self.statuses(pub).values()), {S.PUBLISHED})
        wa = pub.targets.get(platform="whatsapp_status")
        self.assertEqual((wa.external_post_id, wa.permalink), ("MSG-I", ""))

    def test_AC_3_only_pending_targets_are_picked(self):
        """AC-3: `failed`, `uncertain`, `sending` e `published` são ignorados pela fila."""
        pub = self.pub([self.page, self.profile, self.wa])
        statuses = [S.FAILED, S.UNCERTAIN, S.PUBLISHED]
        for target, status in zip(pub.targets.all(), statuses):
            PublicationTarget.objects.filter(pk=target.pk).update(status=status)
        extra = self.pub([self.make_accounts(1, start=7)[0]])
        PublicationTarget.objects.filter(pk=extra.targets.get().pk).update(status=S.SENDING, last_attempt_at=timezone.now())
        self.assertIsNone(self.worker.run_once())
        self.publish.assert_not_called()
        self.assertEqual(sorted(t.status for t in pub.targets.all()), sorted(statuses))

    def test_AC_3_no_request_budget_threads_waits_the_full_configured_time(self):
        """AC-3: sem orçamento por requisição: a espera do container do Threads é a configurada inteira (60 s), não encurtada."""
        pub = self.pub([self.profile])
        clock = Clock()
        fake_time = SimpleNamespace(sleep=clock.sleep, monotonic=clock)
        with override_settings(THREADS_IMAGE_WAIT_SECONDS=60), threads_mocks(statuses=("IN_PROGRESS",)), \
                mock.patch.object(threads_publish, "time", fake_time):
            self.assertEqual(self.worker.run_once(), S.FAILED)  # espera esgotada: falha reenviável, container mantido
        self.assertGreaterEqual(clock.t, 60)
        self.assertEqual(pub.targets.get().error_message, publishing.MSG_THREADS_IMAGE_PENDING)

    def test_AC_3_no_request_budget_evolution_uses_its_own_configured_timeout(self):
        """AC-3: a Evolution recebe `timeout=None` (o cliente usa EVOLUTION_TIMEOUT_SECONDS), sem `min(restante − folga)`."""
        self.pub([self.wa])
        with evolution_mocks() as evo:
            self.worker.run_once()
        self.assertIsNone(evo["send_status_image"].call_args.kwargs["timeout"])

    def test_AC_3_disconnected_account_fails_without_calling_the_platform_and_does_not_block_the_queue(self):
        """AC-3: alvo sem conta vira `failed` ("Conta desconectada") sem chamar a plataforma; o próximo é enviado no ciclo seguinte."""
        orphan = self.pub([self.page])
        PublicationTarget.objects.filter(pk=orphan.targets.get().pk).update(account=None)
        healthy = self.pub([self.page])
        self.assertEqual(self.worker.run_once(), S.FAILED)
        self.publish.assert_not_called()
        orphan_target = orphan.targets.get()
        self.assertEqual((orphan_target.status, orphan_target.error_message), (S.FAILED, publishing.MSG_DISCONNECTED))
        self.assertEqual(self.worker.run_once(), S.PUBLISHED)
        self.assertEqual(healthy.targets.get().status, S.PUBLISHED)

    def test_AC_3_a_lost_claim_or_locked_database_means_idle_not_a_crash(self):
        """AC-3: se a reivindicação não é obtida (outro processo/banco travado) o ciclo devolve None e o alvo segue `pending`."""
        pub = self.pub([self.page])
        with mock.patch.object(publishing, "claim_target", return_value=None):
            self.assertIsNone(self.worker.run_once())
        self.assertEqual(pub.targets.get().status, S.PENDING)
        from django.db import OperationalError

        with mock.patch.object(publishing, "recover_stale_sending", side_effect=OperationalError("database is locked")), \
                self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
            self.assertIsNone(self.worker.run_once())
        self.assertIn("worker_db_locked", "\n".join(logs.output))
        self.assertEqual(pub.targets.get().status, S.PENDING)

    def test_AC_3_unexpected_exception_makes_the_target_uncertain_and_keeps_the_worker_alive(self):
        """AC-3: um bug depois da reivindicação não derruba o worker nem deixa o alvo preso: vira Incerto (`worker_error`); o log só tem o tipo."""
        pub = self.pub([self.page])
        later = self.pub([self.page])
        self.publish.side_effect = [RuntimeError(f"falha com {SECRET}"), {"photo_id": "p", "post_id": "1_77"}]
        with self.assertLogs("apps.social.meta", level=logging.ERROR) as logs:
            self.assertEqual(self.worker.run_once(), S.UNCERTAIN)
        target = pub.targets.get()
        self.assertEqual((target.status, target.error_code, target.error_message), (S.UNCERTAIN, "worker_error", publishing.MSG_UNCERTAIN))
        output = "\n".join(logs.output)
        self.assertIn("worker_error", output)
        self.assertIn("RuntimeError", output)
        self.assertNotIn(SECRET, output)
        self.assertEqual(self.worker.run_once(), S.PUBLISHED)  # o worker segue
        self.assertEqual(later.targets.get().status, S.PUBLISHED)


class RecoveryTests(WorkerBase):
    # ---- AC-7 --------------------------------------------------------------
    def test_AC_7_start_turns_every_sending_target_into_uncertain_and_never_resends(self):
        """AC-7: na partida todo `sending` vira Incerto (`worker_restart`), nenhum é reenviado, e é logado `worker_recovered n=`."""
        a, b = self.pub([self.page]), self.pub([self.page])
        for p in (a, b):
            PublicationTarget.objects.filter(pk=p.targets.get().pk).update(status=S.SENDING, last_attempt_at=timezone.now())
        pending = self.pub([self.page])
        with self.assertLogs("apps.social.meta", level=logging.INFO) as logs:
            recovered = self.worker.start()
        self.assertEqual(recovered, 2)
        for p in (a, b):
            target = p.targets.get()
            self.assertEqual((target.status, target.error_code, target.error_message), (S.UNCERTAIN, "worker_restart", publishing.MSG_UNCERTAIN))
        self.assertEqual(pending.targets.get().status, S.PENDING)  # a fila não é tocada
        self.publish.assert_not_called()
        output = "\n".join(logs.output)
        self.assertIn("worker_recovered n=2", output)
        self.assertIn("worker_started pid=4242", output)

    def test_AC_7_start_without_sending_targets_logs_no_recovery(self):
        """AC-7: sem alvo `sending` nada é recuperado e não há log de recuperação."""
        with self.assertLogs("apps.social.meta", level=logging.INFO) as logs:
            self.assertEqual(self.worker.start(), 0)
        self.assertNotIn("worker_recovered", "\n".join(logs.output))

    def test_AC_7_start_renews_the_heartbeat_row(self):
        """AC-7: a partida registra `started_at`/`beat_at` e o pid do worker."""
        WorkerHeartbeat.beat(pid=1)
        self.worker.start()
        beat = WorkerHeartbeat.objects.get()
        self.assertEqual(beat.pid, 4242)

    # ---- AC-8 --------------------------------------------------------------
    @override_settings(PUBLISH_SENDING_STALE_SECONDS=900)
    def test_AC_8_stale_sending_becomes_uncertain_in_the_next_cycle_and_is_not_resent(self):
        """AC-8: `sending` além de 900 s vira Incerto (`stale`) no ciclo seguinte; o recente não muda; nada é reenviado."""
        old, recent = self.pub([self.page]), self.pub([self.page])
        PublicationTarget.objects.filter(pk=old.targets.get().pk).update(status=S.SENDING, last_attempt_at=timezone.now() - timedelta(seconds=901))
        PublicationTarget.objects.filter(pk=recent.targets.get().pk).update(status=S.SENDING, last_attempt_at=timezone.now() - timedelta(seconds=60))
        self.assertIsNone(self.worker.run_once())
        old_target, recent_target = old.targets.get(), recent.targets.get()
        self.assertEqual((old_target.status, old_target.error_code), (S.UNCERTAIN, "stale"))
        self.assertEqual(recent_target.status, S.SENDING)
        self.publish.assert_not_called()


class LoopAndCommandTests(WorkerBase):
    # ---- AC-15 -------------------------------------------------------------
    def test_AC_15_heartbeat_is_written_every_cycle_with_pid(self):
        """AC-15: cada ciclo grava o heartbeat (`started_at`, `beat_at`, `pid`), inclusive com a fila vazia."""
        self.assertIsNone(self.worker.run_once())
        beat = WorkerHeartbeat.objects.get()
        self.assertEqual((beat.name, beat.pid), ("default", 4242))
        self.assertTrue(WorkerHeartbeat.is_active())
        before = beat.beat_at
        self.worker.run_once()
        self.assertGreaterEqual(WorkerHeartbeat.objects.get().beat_at, before)

    def test_AC_15_idle_sleeps_the_poll_interval_and_busy_does_not(self):
        """AC-15: sem fila dorme WORKER_POLL_SECONDS (2 s); com fila não dorme entre alvos."""
        self.pub([self.page])
        self.pub([self.page])
        processed = self.worker.run(max_cycles=4)  # 2 alvos + 2 ciclos vazios
        self.assertEqual(processed, 2)
        self.assertEqual(self.sleeps, [2, 2])

    def test_AC_15_stop_request_finishes_the_current_target_and_does_not_start_the_next(self):
        """AC-15: pedido de parada (SIGTERM) no meio de um alvo: ele termina e o laço sai sem iniciar o seguinte."""
        first, second = self.pub([self.page]), self.pub([self.page])

        def graph_call(client, page_id, token, **kw):
            self.worker.request_stop()  # o sinal chega durante o envio
            return {"photo_id": "p", "post_id": f"{page_id}_77"}

        self.publish.side_effect = graph_call
        processed = self.worker.run(max_cycles=10)
        self.assertEqual(processed, 1)
        self.assertEqual(first.targets.get().status, S.PUBLISHED)  # terminou o atual
        self.assertEqual(second.targets.get().status, S.PENDING)  # não iniciou o próximo
        self.assertEqual(self.publish.call_count, 1)

    def test_AC_15_signal_handlers_for_sigterm_and_sigint_request_a_graceful_stop(self):
        """AC-15: SIGTERM e SIGINT instalam um handler que só pede a parada."""
        installed = {}
        with mock.patch("apps.social.services.worker.signal.signal", side_effect=lambda sig, handler: installed.setdefault(sig, handler)):
            self.worker.install_signal_handlers()
        self.assertEqual(set(installed), {signal.SIGTERM, signal.SIGINT})
        self.assertFalse(self.worker.stop_event.is_set())
        installed[signal.SIGTERM](signal.SIGTERM, None)
        self.assertTrue(self.worker.stop_event.is_set())

    def test_AC_15_run_worker_once_runs_one_cycle_and_does_not_recover_sending(self):
        """AC-15: `run_worker --once` faz um ciclo (um alvo no máximo) e sai; não faz a recuperação da partida."""
        busy = self.pub([self.page])
        PublicationTarget.objects.filter(pk=busy.targets.get().pk).update(status=S.SENDING, last_attempt_at=timezone.now())
        a, b = self.pub([self.page]), self.pub([self.page])
        out = io.StringIO()
        call_command("run_worker", "--once", stdout=out)
        self.assertIn("published", out.getvalue())
        self.assertEqual(busy.targets.get().status, S.SENDING)  # sem recuperação de partida
        self.assertEqual([a.targets.get().status, b.targets.get().status], [S.PUBLISHED, S.PENDING])  # um alvo só
        out = io.StringIO()
        call_command("run_worker", "--once", stdout=out)
        call_command("run_worker", "--once", stdout=out)
        self.assertIn("fila vazia", out.getvalue())

    def test_AC_15_run_worker_without_once_installs_the_handlers_and_runs_the_loop(self):
        """AC-15: sem `--once` o comando instala os handlers e roda o laço até a parada."""
        with mock.patch("apps.social.management.commands.run_worker.Worker") as worker_cls:
            worker_cls.return_value.run.return_value = 3
            out = io.StringIO()
            call_command("run_worker", stdout=out)
        worker_cls.return_value.install_signal_handlers.assert_called_once()
        worker_cls.return_value.run.assert_called_once()
        self.assertIn("3 alvo(s)", out.getvalue())

    @override_settings(WORKER_HEARTBEAT_STALE_SECONDS=180)
    def test_AC_15_worker_health_exit_code_follows_the_heartbeat(self):
        """AC-15: `worker_health` sai com 0 se o heartbeat é recente e com 1 se ausente ou vencido; mostra a fila."""
        self.pub([self.page])
        err = io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            call_command("worker_health", stderr=err)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("worker inativo; fila=1", err.getvalue())
        WorkerHeartbeat.beat(pid=1)
        out = io.StringIO()
        call_command("worker_health", stdout=out)  # não levanta: código 0
        self.assertIn("worker ativo; fila=1", out.getvalue())
        WorkerHeartbeat.objects.update(beat_at=timezone.now() - timedelta(seconds=181))
        with self.assertRaises(SystemExit) as ctx:
            call_command("worker_health", stderr=io.StringIO())
        self.assertEqual(ctx.exception.code, 1)

    def test_AC_15_logs_carry_only_ids_platform_and_status(self):
        """AC-15/AC-17: os logs do worker não trazem chave, token, texto da publicação nem o nome da conta."""
        self.pub([self.wa], text=f"Texto {SECRET}")
        with evolution_mocks(), self.assertLogs("apps.social.meta", level=logging.INFO) as logs:
            self.worker.run_once()
        output = "\n".join(logs.output)
        self.assertIn("worker_target_claimed", output)
        self.assertIn("worker_target_done", output)
        for secret in (SECRET, "chave-da-loja", "loja"):
            self.assertNotIn(secret, output)
