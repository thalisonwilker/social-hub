"""Reivindicação atômica (spec 0007, AC-4): só `pending` é reivindicado e exatamente um processo o recebe."""
import threading
from datetime import timedelta
from unittest import mock

from django.db import OperationalError, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services import publishing

S = PublicationTarget.Status


def make_target(owner, *, status=S.PENDING, with_account=True, key="1"):
    pub = Publication.objects.create(owner=owner, text="Olá")
    account = None
    if with_account:
        account = SocialAccount(owner=owner, platform="threads", external_id=key, name=f"A{key}")
        account.set_token("t")
        account.save()
    return PublicationTarget.objects.create(
        publication=pub, account=account, page_external_id=key, page_name=f"Alvo {key}", platform="threads", status=status
    )


class ClaimRulesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        cls.alice = get_user_model().objects.create_user("alice", password="x")

    def test_AC_4_only_a_pending_target_is_claimed(self):
        """AC-4: `pending` → `sending` (com tentativa +1); sending/failed/uncertain/published nunca são reivindicados."""
        for index, status in enumerate((S.SENDING, S.FAILED, S.UNCERTAIN, S.PUBLISHED)):
            with self.subTest(status=status):
                target = make_target(self.alice, status=status, key=f"x{index}")
                self.assertIsNone(publishing.claim_target(target.pk))
                target.refresh_from_db()
                self.assertEqual((target.status, target.attempts), (status, 0))
        pending = make_target(self.alice, key="p")
        claimed = publishing.claim_target(pending.pk)
        self.assertEqual((claimed.status, claimed.attempts), (S.SENDING, 1))
        self.assertIsNotNone(claimed.last_attempt_at)
        self.assertIsNone(publishing.claim_target(pending.pk))

    def test_AC_4_a_stale_sending_target_is_not_reclaimed(self):
        """AC-4: `sending` antigo NÃO é reivindicado de novo (fim da recuperação automática da issue #1)."""
        target = make_target(self.alice, status=S.SENDING)
        PublicationTarget.objects.filter(pk=target.pk).update(last_attempt_at=timezone.now() - timedelta(hours=3))
        self.assertIsNone(publishing.claim_target(target.pk))

    def test_AC_4_a_target_without_an_account_is_not_claimed(self):
        """AC-4: conta desconectada → não reivindica."""
        self.assertIsNone(publishing.claim_target(make_target(self.alice, with_account=False).pk))

    def test_AC_4_a_locked_database_means_not_claimed_and_nothing_is_lost(self):
        """AC-4: `database is locked` → devolve None (o worker repete depois) e o alvo continua `pending`."""
        target = make_target(self.alice)
        with mock.patch("apps.social.services.publishing.PublicationTarget.objects") as objects:
            objects.filter.return_value.update.side_effect = OperationalError("database is locked")
            self.assertIsNone(publishing.claim_target(target.pk))
        target.refresh_from_db()
        self.assertEqual(target.status, S.PENDING)

    def test_AC_4_requeue_only_moves_failed_targets_with_an_account(self):
        """AC-4: `failed → pending` (limpa erro) só para `failed` com conta; nenhum outro estado muda."""
        failed = make_target(self.alice, status=S.FAILED, key="f")
        PublicationTarget.objects.filter(pk=failed.pk).update(error_message="x", error_code="y")
        self.assertTrue(publishing.requeue_target(failed.pk))
        failed.refresh_from_db()
        self.assertEqual((failed.status, failed.error_message, failed.error_code), (S.PENDING, "", ""))
        self.assertFalse(publishing.requeue_target(failed.pk))  # já está pending
        for index, status in enumerate((S.SENDING, S.UNCERTAIN, S.PUBLISHED)):
            other = make_target(self.alice, status=status, key=f"o{index}")
            self.assertFalse(publishing.requeue_target(other.pk))
            other.refresh_from_db()
            self.assertEqual(other.status, status)
        self.assertFalse(publishing.requeue_target(make_target(self.alice, status=S.FAILED, with_account=False, key="n").pk))

    def test_AC_4_recover_sending_goes_to_uncertain_and_never_to_pending(self):
        """AC-4: `sending → uncertain` com o motivo; só os que passaram do prazo, quando há prazo; nada vai para `pending`."""
        old = make_target(self.alice, status=S.SENDING, key="old")
        new = make_target(self.alice, status=S.SENDING, key="new")
        PublicationTarget.objects.filter(pk=old.pk).update(last_attempt_at=timezone.now() - timedelta(hours=1))
        PublicationTarget.objects.filter(pk=new.pk).update(last_attempt_at=timezone.now())
        self.assertEqual(publishing.recover_stale_sending(), 1)
        old.refresh_from_db(), new.refresh_from_db()
        self.assertEqual((old.status, old.error_code), (S.UNCERTAIN, "stale"))
        self.assertEqual(new.status, S.SENDING)
        self.assertEqual(publishing.recover_sending(reason="worker_restart"), 1)
        new.refresh_from_db()
        self.assertEqual((new.status, new.error_code), (S.UNCERTAIN, "worker_restart"))
        self.assertFalse(PublicationTarget.objects.filter(status=S.PENDING).exists())


class ConcurrentClaimTests(TransactionTestCase):
    """AC-4: várias conexões reais disputam o mesmo alvo; exatamente uma o recebe."""

    def test_AC_4_exactly_one_of_many_concurrent_claims_wins(self):
        from django.contrib.auth import get_user_model

        owner = get_user_model().objects.create_user("alice", password="x")
        targets = [make_target(owner, key=str(i)) for i in range(5)]
        for target in targets:
            winners, barrier = [], threading.Barrier(6)

            def attempt():
                try:
                    barrier.wait(timeout=5)
                    claimed = publishing.claim_target(target.pk)
                    winners.append(claimed is not None)
                finally:
                    connection.close()

            threads = [threading.Thread(target=attempt) for _ in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)
            self.assertEqual(len(winners), 6)
            self.assertEqual(sum(winners), 1, "exatamente um processo deve reivindicar o alvo")
            target.refresh_from_db()
            self.assertEqual((target.status, target.attempts), (S.SENDING, 1))
