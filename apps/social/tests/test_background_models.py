import importlib
import itertools
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.social import conf
from apps.social.models import Publication, PublicationTarget, SocialAccount, WorkerHeartbeat

S = PublicationTarget.Status
_ids = itertools.count(1)


class TargetStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice", password="x")

    def pub_with(self, *statuses, with_account=True):
        pub = Publication.objects.create(owner=self.alice, text="Olá")
        account = None
        if with_account:
            account = SocialAccount(owner=self.alice, platform="threads", external_id=str(next(_ids)), name="Maria")
            account.set_token("t")
            account.save()
        for i, status in enumerate(statuses):
            PublicationTarget.objects.create(
                publication=pub, account=account, page_external_id=f"p{i}", page_name=f"Alvo {i}", platform="threads", status=status
            )
        return pub

    # ---- AC-11: status geral e contagens -----------------------------------
    def test_AC_11_overall_status_precedence_is_failed_then_uncertain_then_published_then_pending(self):
        """AC-11: failed > uncertain > published (todos) > pending."""
        cases = [
            ((S.FAILED, S.UNCERTAIN, S.PUBLISHED, S.PENDING), Publication.Status.FAILED),
            ((S.UNCERTAIN, S.PUBLISHED, S.PENDING), Publication.Status.UNCERTAIN),
            ((S.UNCERTAIN, S.PUBLISHED), Publication.Status.UNCERTAIN),
            ((S.UNCERTAIN, S.SENDING), Publication.Status.UNCERTAIN),
            ((S.PUBLISHED, S.PUBLISHED), Publication.Status.PUBLISHED),
            ((S.PUBLISHED, S.PENDING), Publication.Status.PENDING),
            ((S.SENDING,), Publication.Status.PENDING),
            ((), Publication.Status.PENDING),
        ]
        for statuses, expected in cases:
            with self.subTest(statuses=[str(s) for s in statuses]):
                self.assertEqual(self.pub_with(*statuses).status, expected)

    def test_AC_11_the_overall_label_for_uncertainty_is_incerta(self):
        """AC-11: o rótulo geral é "Incerta"; o do alvo é "Incerto"."""
        self.assertEqual(self.pub_with(S.UNCERTAIN).status_label, "Incerta")
        self.assertEqual(PublicationTarget.Status.UNCERTAIN.label, "Incerto")
        self.assertEqual(PublicationTarget.Status.UNCERTAIN.value, "uncertain")

    def test_AC_11_counts_include_the_uncertain_state(self):
        """AC-11: as contagens por estado incluem `uncertain`."""
        counts = self.pub_with(S.UNCERTAIN, S.UNCERTAIN, S.PUBLISHED, S.FAILED).status_counts()
        self.assertEqual(counts["uncertain"], 2)
        self.assertEqual((counts["published"], counts["failed"], counts["pending"], counts["sending"]), (1, 1, 0, 0))

    def test_AC_11_resolvable_and_try_again_follow_the_state(self):
        """AC-11: só `uncertain` é resolvível; "Tentar novamente" só vale para `failed` com conta; incerto nunca é reenviado como retentável."""
        pub = self.pub_with(S.UNCERTAIN, S.FAILED, S.PENDING, S.SENDING, S.PUBLISHED)
        by_status = {t.status: t for t in pub.targets.all()}
        self.assertEqual({s: t.is_resolvable for s, t in by_status.items()},
                         {S.UNCERTAIN: True, S.FAILED: False, S.PENDING: False, S.SENDING: False, S.PUBLISHED: False})
        self.assertEqual({s: t.can_try_again for s, t in by_status.items()},
                         {S.UNCERTAIN: False, S.FAILED: True, S.PENDING: False, S.SENDING: False, S.PUBLISHED: False})
        self.assertFalse(by_status[S.UNCERTAIN].is_retryable)  # o Incerto não é "retentável" automático

    def test_AC_11_can_try_again_needs_an_account_and_resend_too(self):
        """AC-11: sem conta, `failed` não pode tentar de novo e `uncertain` não pode ser reenviado (mas segue resolvível)."""
        pub = self.pub_with(S.FAILED, S.UNCERTAIN, with_account=False)
        failed, uncertain = pub.targets.get(status=S.FAILED), pub.targets.get(status=S.UNCERTAIN)
        self.assertFalse(failed.can_try_again)
        self.assertTrue(uncertain.is_resolvable)
        self.assertFalse(uncertain.can_resend)
        with_account = self.pub_with(S.UNCERTAIN).targets.get()
        self.assertTrue(with_account.can_resend)

    def test_AC_11_has_resolvable_targets_on_the_publication(self):
        """AC-11: a publicação informa se há alvo a resolver."""
        self.assertTrue(self.pub_with(S.PUBLISHED, S.UNCERTAIN).has_resolvable_targets)
        self.assertFalse(self.pub_with(S.PUBLISHED, S.FAILED).has_resolvable_targets)


class WorkerHeartbeatTests(TestCase):
    # ---- AC-18 / AC-14 (base): heartbeat ---------------------------------------
    def test_AC_18_heartbeat_is_a_single_row_updated_in_place(self):
        """AC-18: `WorkerHeartbeat` é uma linha só (name=default): bater de novo atualiza `beat_at` e mantém `started_at`."""
        first = WorkerHeartbeat.beat(pid=100)
        started = first.started_at
        second = WorkerHeartbeat.beat(pid=100)
        self.assertEqual(WorkerHeartbeat.objects.count(), 1)
        self.assertEqual(second.name, "default")
        self.assertEqual(second.started_at, started)
        self.assertGreaterEqual(second.beat_at, first.beat_at)

    def test_AC_18_a_new_worker_process_resets_started_at(self):
        """AC-18: `start()` (nova partida) renova `started_at` e o pid."""
        WorkerHeartbeat.beat(pid=1)
        beat = WorkerHeartbeat.start(pid=2)
        self.assertEqual((beat.pid, WorkerHeartbeat.objects.count()), (2, 1))

    @override_settings(WORKER_HEARTBEAT_STALE_SECONDS=180)
    def test_AC_18_active_means_a_recent_beat(self):
        """AC-18: ativo ⇔ `beat_at` mais recente que WORKER_HEARTBEAT_STALE_SECONDS; sem linha = inativo."""
        now = timezone.now()
        self.assertFalse(WorkerHeartbeat.is_active(now=now))
        WorkerHeartbeat.beat(pid=1)
        self.assertTrue(WorkerHeartbeat.is_active(now=now))
        self.assertTrue(WorkerHeartbeat.is_active(now=now + timedelta(seconds=179)))
        self.assertFalse(WorkerHeartbeat.is_active(now=now + timedelta(seconds=181)))

    def test_AC_18_beat_never_stores_secrets_or_content(self):
        """AC-18: a linha guarda só nome, datas e pid."""
        fields = {f.name for f in WorkerHeartbeat._meta.concrete_fields}
        self.assertEqual(fields, {"id", "name", "started_at", "beat_at", "pid"})


class PublishModeConfigTests(SimpleTestCase):
    def test_AC_18_settings_defaults(self):
        """AC-18: defaults das quatro settings novas."""
        self.assertEqual(settings.WORKER_POLL_SECONDS, 2)
        self.assertEqual(settings.WORKER_HEARTBEAT_STALE_SECONDS, 180)
        self.assertEqual(settings.PUBLISH_SENDING_STALE_SECONDS, 900)

    @override_settings(PUBLISH_MODE="worker")
    def test_AC_18_publish_mode_worker(self):
        """AC-18: `publish_mode()` devolve `worker` quando configurado."""
        self.assertEqual(conf.publish_mode(), "worker")
        self.assertTrue(conf.publish_in_background())

    @override_settings(PUBLISH_MODE="inline")
    def test_AC_18_publish_mode_inline(self):
        """AC-18: `inline` envia na requisição."""
        self.assertEqual(conf.publish_mode(), "inline")
        self.assertFalse(conf.publish_in_background())

    def test_AC_18_unknown_values_fall_back_to_inline_the_safe_legacy_mode(self):
        """AC-18: valor inválido cai em `inline` (comportamento antigo, sem perda de dados)."""
        for value in ("", "Worker ", "celery", None):
            with self.subTest(value=value), override_settings(PUBLISH_MODE=value):
                self.assertEqual(conf.publish_mode(), "inline")

    def test_AC_18_the_test_runner_forces_inline_even_with_production_settings(self):
        """AC-18: a suíte roda em `inline` (o container usa settings de produção, cujo padrão é `worker`)."""
        self.assertEqual(settings.PUBLISH_MODE, "inline")

    def test_AC_18_production_defaults_to_the_worker_mode(self):
        """AC-18: `config.settings.prod` usa `worker` por padrão (`PUBLISH_MODE` do ambiente pode sobrescrever)."""
        source = (settings.BASE_DIR / "config" / "settings" / "prod.py").read_text(encoding="utf-8")
        self.assertIn('PUBLISH_MODE = os.environ.get("PUBLISH_MODE") or "worker"', source)  # vazio no .env também cai em worker


class MigrationIsAdditiveTests(SimpleTestCase):
    def test_AC_18_the_migration_only_adds_state_and_a_table(self):
        """AC-18: a migração da feature só adiciona o estado `uncertain` (AlterField de choices) e cria `WorkerHeartbeat`."""
        module = importlib.import_module("apps.social.migrations.0005_background_publishing")
        kinds = sorted(type(op).__name__ for op in module.Migration.operations)
        self.assertEqual(kinds, ["AlterField", "CreateModel"])
        self.assertEqual(module.Migration.operations[0].__class__.__name__ in ("AlterField", "CreateModel"), True)
        for op in module.Migration.operations:
            self.assertNotIn(type(op).__name__, {"DeleteModel", "RemoveField", "RenameField", "RunSQL", "RunPython"})
