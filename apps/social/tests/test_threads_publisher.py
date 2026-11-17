import logging
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.social.images import sanitize_image
from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services import publishing, threads_publish
from apps.social.services.meta import MetaApiError
from apps.social.services.threads import ThreadsClient

from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status
TEXT = "Texto confidencial para o Threads ☕"
PERMALINK = "https://www.threads.com/@maria/post/abc"


class Clock:
    """Relógio falso: `sleep` avança o tempo, sem esperar de verdade."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class threads_mocks:
    """Patches de ThreadsClient com um ciclo de container feliz por padrão."""

    def __init__(self, statuses=("FINISHED",), **overrides):
        self.statuses = list(statuses)
        self.overrides = overrides

    def __enter__(self):
        def status(container_id, token):
            current = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return {"status": current, "error_message": ""}

        defaults = {
            "create_text_container": {"return_value": "c-1"},
            "container_status": {"side_effect": status},
            "publish_container": {"return_value": "m-1"},
            "get_permalink": {"return_value": PERMALINK},
            "refresh_token": {"return_value": {"access_token": "token-renovado", "expires_in": 5184000}},
        }
        self.patchers, self.mocks = [], {}
        for name, kwargs in defaults.items():
            kwargs = {**kwargs, **self.overrides.get(name, {})}
            patcher = mock.patch.object(ThreadsClient, name, **kwargs)
            self.mocks[name] = patcher.start()
            self.patchers.append(patcher)
        return self.mocks

    def __exit__(self, *exc):
        for patcher in self.patchers:
            patcher.stop()


# ---------------------------------------------------------------------------- publicador isolado
@override_settings(**THREADS_SETTINGS)
class PublishTextTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.account = make_threads_account(self.alice)
        self.publication = publishing.create_publication(self.alice, TEXT, None, [self.account])
        self.target = self.publication.targets.select_related("account").get()
        self.client_mock = mock.create_autospec(ThreadsClient, instance=True)
        self.client_mock.create_text_container.return_value = "c-1"
        self.client_mock.publish_container.return_value = "m-1"
        self.client_mock.get_permalink.return_value = PERMALINK
        self.clock = Clock()

    def run_publish(self, statuses):
        queue = list(statuses)
        self.client_mock.container_status.side_effect = lambda c, t: {"status": queue.pop(0) if len(queue) > 1 else queue[0], "error_message": ""}
        return threads_publish.publish_text(self.target, self.client_mock, "tok", TEXT, sleep=self.clock.sleep, clock=self.clock)

    def test_AC_17_creates_container_remembers_its_id_then_publishes_and_reads_the_permalink(self):
        """AC-17: container TEXT criado, id gravado no alvo ANTES de esperar, publicado e permalink lido."""
        def status(container_id, token):
            self.target.refresh_from_db()
            assert self.target.external_container_id == "c-1"  # já gravado antes da consulta
            return {"status": "FINISHED", "error_message": ""}

        self.client_mock.container_status.side_effect = status
        outcome = threads_publish.publish_text(self.target, self.client_mock, "tok", TEXT, sleep=self.clock.sleep, clock=self.clock)
        self.assertEqual((outcome.post_id, outcome.permalink), ("m-1", PERMALINK))
        self.client_mock.create_text_container.assert_called_once_with(self.account.external_id, "tok", TEXT)
        self.client_mock.publish_container.assert_called_once_with(self.account.external_id, "tok", "c-1")
        self.client_mock.get_permalink.assert_called_once_with("m-1", "tok")

    def test_AC_17_polls_while_in_progress(self):
        """AC-17: enquanto IN_PROGRESS consulta de novo a cada 2 s, até FINISHED."""
        self.run_publish(["IN_PROGRESS", "IN_PROGRESS", "FINISHED"])
        self.assertEqual(self.client_mock.container_status.call_count, 3)
        self.assertEqual(self.clock.t, 4.0)

    def test_AC_18_not_ready_within_the_limit_raises_and_keeps_the_container(self):
        """AC-18: sem FINISHED dentro do limite → ContainerNotReady, com o id mantido para retomar."""
        with self.assertRaises(threads_publish.ContainerNotReady):
            self.run_publish(["IN_PROGRESS"])
        self.client_mock.publish_container.assert_not_called()
        self.target.refresh_from_db()
        self.assertEqual(self.target.external_container_id, "c-1")
        self.assertGreaterEqual(self.clock.t, 20.0)

    @override_settings(THREADS_CONTAINER_WAIT_SECONDS=4)
    def test_AC_18_wait_limit_comes_from_the_setting(self):
        """AC-18: o tempo máximo de espera vem de THREADS_CONTAINER_WAIT_SECONDS."""
        with self.assertRaises(threads_publish.ContainerNotReady):
            self.run_publish(["IN_PROGRESS"])
        self.assertEqual(self.clock.t, 4.0)

    def test_AC_18_resumes_an_existing_container_without_creating_another(self):
        """AC-18: alvo com container válido reutiliza o id e só publica quando estiver FINISHED."""
        PublicationTarget.objects.filter(pk=self.target.pk).update(external_container_id="c-existente")
        self.target.refresh_from_db()
        outcome = self.run_publish(["FINISHED"])
        self.client_mock.create_text_container.assert_not_called()
        self.client_mock.publish_container.assert_called_once_with(self.account.external_id, "tok", "c-existente")
        self.assertEqual(outcome.post_id, "m-1")

    def test_AC_18_error_and_expired_raise_container_failed(self):
        """AC-18: ERROR e EXPIRED levantam ContainerFailed com o status."""
        for status in ("ERROR", "EXPIRED"):
            with self.subTest(status), self.assertRaises(threads_publish.ContainerFailed) as ctx:
                self.run_publish([status])
            self.assertEqual(ctx.exception.status, status)
            self.client_mock.publish_container.assert_not_called()
            PublicationTarget.objects.filter(pk=self.target.pk).update(external_container_id="")
            self.target.refresh_from_db()

    def test_AC_19_already_published_container_is_not_published_again(self):
        """AC-19: container PUBLISHED → resultado sem id/link e nenhuma segunda publicação."""
        PublicationTarget.objects.filter(pk=self.target.pk).update(external_container_id="c-existente")
        self.target.refresh_from_db()
        outcome = self.run_publish(["PUBLISHED"])
        self.assertEqual((outcome.post_id, outcome.permalink), ("", ""))
        self.client_mock.publish_container.assert_not_called()

    def test_AC_17_permalink_failure_does_not_undo_the_publication(self):
        """AC-17: se ler o permalink falhar, o post já publicado vale; link vazio."""
        self.client_mock.get_permalink.side_effect = MetaApiError("x", code="network")
        outcome = self.run_publish(["FINISHED"])
        self.assertEqual((outcome.post_id, outcome.permalink), ("m-1", ""))


# ---------------------------------------------------------------------------- despacho por plataforma
@override_settings(**THREADS_SETTINGS)
class ThreadsDispatchTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.threads = make_threads_account(self.alice, "900", username="maria")

    def publication(self, accounts, text=TEXT, image=False):
        sanitized = sanitize_image(make_upload()) if image else None
        return publishing.create_publication(self.alice, text, sanitized, accounts)

    def target(self, pub, platform="threads"):
        return pub.targets.get(platform=platform)

    # ---- AC-17 / AC-21 ---------------------------------------------------
    def test_AC_17_publishes_text_to_threads_without_any_image(self):
        """AC-17: alvo só do Threads: container → publica → permalink; nada de imagem; token renovado se devido."""
        pub = self.publication([self.threads])
        self.assertFalse(pub.has_image)
        with threads_mocks() as api:
            result = publishing.send_pending(pub)
        self.assertEqual((result.attempted, result.published, result.failed), (1, 1, 0))
        api["create_text_container"].assert_called_once_with("900", "threads-long-token", TEXT)
        target = self.target(pub)
        self.assertEqual((target.status, target.external_post_id, target.permalink), (S.PUBLISHED, "m-1", PERMALINK))
        self.assertEqual((target.attempts, target.error_message), (1, ""))
        self.assertEqual(pub.status, Publication.Status.PUBLISHED)
        self.publish.assert_not_called()  # nenhuma chamada de foto do Facebook

    def test_AC_21_mixed_targets_each_follow_their_own_platform_flow(self):
        """AC-21: Facebook recebe foto + texto como na 0003; Threads só texto; resultado por alvo."""
        page = self.make_accounts(1)[0]
        pub = self.publication([page, self.threads], image=True)
        with threads_mocks() as api:
            result = publishing.send_pending(pub)
        self.assertEqual((result.attempted, result.published, result.failed), (2, 2, 0))
        self.assertEqual(self.publish.call_count, 1)
        self.assertEqual(self.publish.call_args.args[1], page.external_id)
        self.assertEqual(self.publish.call_args.kwargs["message"], TEXT)
        self.assertEqual(self.publish.call_args.kwargs["content_type"], "image/jpeg")
        api["create_text_container"].assert_called_once()
        self.assertNotIn("image", str(api["create_text_container"].call_args))
        fb, th = self.target(pub, "facebook_page"), self.target(pub, "threads")
        self.assertEqual(fb.permalink, f"https://www.facebook.com/{page.external_id}_77")
        self.assertEqual(th.permalink, PERMALINK)

    def test_AC_21_partial_failure_then_retry_only_resends_the_failed_target(self):
        """AC-21: Threads falha, Facebook publica; o retry reenvia só o Threads (Facebook nunca de novo)."""
        page = self.make_accounts(1)[0]
        pub = self.publication([page, self.threads], image=True)
        with threads_mocks(create_text_container={"side_effect": MetaApiError("x", code="network")}):
            first = publishing.send_pending(pub)
        self.assertEqual((first.published, first.failed), (1, 1))
        self.assertEqual(pub.status, Publication.Status.FAILED)
        self.publish.reset_mock()
        with threads_mocks():
            second = publishing.send_pending(pub)
        self.assertEqual((second.attempted, second.published), (1, 1))
        self.publish.assert_not_called()
        self.assertEqual(pub.status, Publication.Status.PUBLISHED)

    def test_AC_21_batch_limit_applies_to_both_platforms_together(self):
        """AC-21: o lote de 5 conta alvos de todas as plataformas."""
        pages = self.make_accounts(3)
        profiles = [make_threads_account(self.alice, f"90{i}", username=f"u{i}") for i in range(1, 5)]
        pub = self.publication(pages + profiles, image=True)
        with threads_mocks():
            first = publishing.send_pending(pub, batch_size=5)
            second = publishing.send_pending(pub, batch_size=5)
        self.assertEqual((first.attempted, first.remaining), (5, 2))
        self.assertEqual((second.attempted, second.remaining), (2, 0))

    # ---- AC-12 -----------------------------------------------------------
    def test_AC_12_due_token_is_refreshed_before_creating_the_container(self):
        """AC-12: token a vencer é renovado antes de publicar; o novo token é o usado."""
        due = make_threads_account(self.alice, "902", days_left=5, refreshed_hours_ago=48, token="token-antigo")
        pub = self.publication([due])
        order = mock.Mock()
        with threads_mocks() as api:
            order.attach_mock(api["refresh_token"], "refresh")
            order.attach_mock(api["create_text_container"], "create")
            publishing.send_pending(pub)
        self.assertEqual([c[0] for c in order.mock_calls], ["refresh", "create"])
        api["refresh_token"].assert_called_once_with("token-antigo")
        api["create_text_container"].assert_called_once_with("902", "token-renovado", TEXT)

    def test_AC_12_expired_token_fails_the_target_without_calling_threads(self):
        """AC-12: token já vencido → alvo falha com Reconexão necessária, conta needs_reauth, nenhuma chamada."""
        expired = make_threads_account(self.alice, "903", days_left=-1)
        pub = self.publication([expired])
        with threads_mocks() as api:
            publishing.send_pending(pub)
        for mock_ in api.values():
            mock_.assert_not_called()
        target = self.target(pub)
        self.assertEqual((target.status, target.error_message), (S.FAILED, publishing.MSG_THREADS_REAUTH))
        expired.refresh_from_db()
        self.assertEqual(expired.status, SocialAccount.Status.NEEDS_REAUTH)

    # ---- AC-20 -----------------------------------------------------------
    def test_AC_20_error_mapping_for_threads_targets(self):
        """AC-20: token, limite (429), rede e outros códigos viram mensagens amigáveis; token marca needs_reauth."""
        cases = [
            (MetaApiError("x", code=190), publishing.MSG_THREADS_REAUTH, True, False),
            (MetaApiError("x", status=401), publishing.MSG_THREADS_REAUTH, True, False),
            (MetaApiError("x", status=429), publishing.MSG_RATE_LIMIT, False, True),
            (MetaApiError("x", code=4), publishing.MSG_RATE_LIMIT, False, True),
            (MetaApiError("x", code="network"), publishing.MSG_NETWORK, False, True),
            (MetaApiError("x", code="bad_response"), publishing.MSG_NETWORK, False, True),
            (MetaApiError("texto cru com segredo", code=100), "A Meta recusou a publicação (código 100).", False, True),
        ]
        for i, (error, message, reauth, retryable) in enumerate(cases):
            with self.subTest(code=error.code, status=error.status):
                account = make_threads_account(self.alice, f"95{i}", username=f"e{i}")
                pub = self.publication([account])
                with threads_mocks(create_text_container={"side_effect": error}):
                    publishing.send_pending(pub)
                target = self.target(pub)
                self.assertEqual((target.status, target.error_message), (S.FAILED, message))
                self.assertNotIn("segredo", target.error_message)
                account.refresh_from_db()
                self.assertEqual(account.status == SocialAccount.Status.NEEDS_REAUTH, reauth)
                self.assertEqual(target.is_retryable, True)

    # ---- AC-18 / AC-19 ---------------------------------------------------
    @override_settings(THREADS_CONTAINER_WAIT_SECONDS=0)
    def test_AC_18_container_not_ready_keeps_the_id_and_the_retry_resumes_it(self):
        """AC-18: container que não fica pronto → falha reenviável com o id mantido; o retry reutiliza o mesmo container."""
        pub = self.publication([self.threads])
        with threads_mocks(statuses=["IN_PROGRESS"]) as api:
            publishing.send_pending(pub)
        target = self.target(pub)
        self.assertEqual((target.status, target.error_message, target.external_container_id),
                         (S.FAILED, publishing.MSG_THREADS_PENDING, "c-1"))
        with threads_mocks(statuses=["FINISHED"]) as api2:
            publishing.send_pending(pub)
        api2["create_text_container"].assert_not_called()  # reutilizou o container
        api2["publish_container"].assert_called_once_with("900", "threads-long-token", "c-1")
        target.refresh_from_db()
        self.assertEqual((target.status, target.attempts), (S.PUBLISHED, 2))

    def test_AC_18_error_status_discards_the_container_and_the_retry_creates_a_new_one(self):
        """AC-18: ERROR → falha, id descartado; o próximo envio cria outro container."""
        pub = self.publication([self.threads])
        with threads_mocks(statuses=["ERROR"]):
            publishing.send_pending(pub)
        target = self.target(pub)
        self.assertEqual((target.status, target.error_message, target.external_container_id),
                         (S.FAILED, publishing.MSG_THREADS_REJECTED, ""))
        with threads_mocks(create_text_container={"return_value": "c-2"}) as api:
            publishing.send_pending(pub)
        api["create_text_container"].assert_called_once()
        target.refresh_from_db()
        self.assertEqual((target.status, target.external_container_id), (S.PUBLISHED, "c-2"))

    def test_AC_18_expired_status_has_its_own_message_and_discards_the_id(self):
        """AC-18: EXPIRED → mensagem de expiração e id descartado."""
        pub = self.publication([self.threads])
        with threads_mocks(statuses=["EXPIRED"]):
            publishing.send_pending(pub)
        target = self.target(pub)
        self.assertEqual((target.error_message, target.external_container_id), (publishing.MSG_THREADS_EXPIRED, ""))

    def test_AC_19_already_published_container_marks_published_without_republishing(self):
        """AC-19: container PUBLISHED → alvo published sem link e sem chamar threads_publish."""
        pub = self.publication([self.threads])
        PublicationTarget.objects.filter(publication=pub).update(external_container_id="c-antigo")
        with threads_mocks(statuses=["PUBLISHED"]) as api:
            publishing.send_pending(pub)
        api["publish_container"].assert_not_called()
        api["create_text_container"].assert_not_called()
        target = self.target(pub)
        self.assertEqual((target.status, target.external_post_id, target.permalink), (S.PUBLISHED, "", ""))

    # ---- AC-22 -----------------------------------------------------------
    def test_AC_22_concurrent_claims_send_only_once_and_published_is_never_resent(self):
        """AC-22: o segundo claim não recebe o alvo; published nunca é reenviado."""
        pub = self.publication([self.threads])
        target = self.target(pub)
        self.assertIsNotNone(publishing.claim_target(target.pk))
        self.assertIsNone(publishing.claim_target(target.pk))
        PublicationTarget.objects.filter(pk=target.pk).update(status=S.PUBLISHED)
        self.assertIsNone(publishing.claim_target(target.pk))

    def test_AC_22_recent_sending_is_skipped_and_stale_sending_resumes_by_container_id(self):
        """AC-22: sending < 5 min não reenvia; ≥ 5 min é recuperado (log) e retoma pelo container já gravado."""
        pub = self.publication([self.threads])
        target = self.target(pub)
        PublicationTarget.objects.filter(pk=target.pk).update(
            status=S.SENDING, last_attempt_at=timezone.now() - timedelta(minutes=1), external_container_id="c-preso")
        with threads_mocks() as api:
            self.assertEqual(publishing.send_pending(pub).attempted, 0)
        api["create_text_container"].assert_not_called()
        PublicationTarget.objects.filter(pk=target.pk).update(last_attempt_at=timezone.now() - timedelta(minutes=6))
        with threads_mocks() as api, self.assertLogs("apps.social.meta", level=logging.WARNING) as logs:
            result = publishing.send_pending(pub)
        self.assertEqual(result.published, 1)
        api["create_text_container"].assert_not_called()  # retomou pelo container
        api["publish_container"].assert_called_once_with("900", "threads-long-token", "c-preso")
        self.assertIn("target_reclaimed", "\n".join(logs.output))

    # ---- demais ----------------------------------------------------------
    @override_settings(THREADS_APP_SECRET="")
    def test_AC_20_not_configured_fails_the_target_without_calling_threads(self):
        """AC-20: sem THREADS_* o alvo falha com aviso e nada é chamado."""
        pub = self.publication([self.threads])
        with threads_mocks() as api:
            publishing.send_pending(pub)
        for mock_ in api.values():
            mock_.assert_not_called()
        self.assertEqual(self.target(pub).error_message, publishing.MSG_THREADS_NOT_CONFIGURED)

    def test_AC_21_disconnected_threads_account_fails_with_the_snapshot(self):
        """AC-21: perfil desconectado antes do envio → 'Conta desconectada.', sem chamadas, com o nome preservado."""
        pub = self.publication([self.threads])
        self.threads.delete()
        with threads_mocks() as api:
            publishing.send_pending(pub)
        api["create_text_container"].assert_not_called()
        target = self.target(pub)
        self.assertEqual((target.status, target.error_message, target.page_name), (S.FAILED, publishing.MSG_DISCONNECTED, "Maria"))
        self.assertFalse(target.is_retryable)

    def test_AC_23_threads_only_publication_writes_no_file_and_snapshots_the_platform(self):
        """AC-23: publicação só do Threads não grava arquivo e o alvo guarda a plataforma."""
        pub = self.publication([self.threads])
        self.assertEqual((pub.image.name, pub.image_content_type), ("", ""))
        self.assertEqual([p for p in Path(self.media).rglob("*") if p.is_file()], [])
        self.assertEqual(self.target(pub).platform, "threads")

    def test_AC_25_logs_never_contain_the_text_or_tokens(self):
        """AC-25: logs de publicação no Threads não trazem texto, tokens nem URLs."""
        ok = self.publication([self.threads])
        failing_account = make_threads_account(self.alice, "970", username="falha", token="token-secreto-xyz")
        failing = self.publication([failing_account])
        with self.assertLogs("apps.social.meta", level=logging.INFO) as logs:
            with threads_mocks():
                publishing.send_pending(ok)
            with threads_mocks(create_text_container={"side_effect": MetaApiError(f"{TEXT} token-secreto-xyz", code=100)}):
                publishing.send_pending(failing)
        output = "\n".join(logs.output)
        for secret in (TEXT, "threads-long-token", "token-secreto-xyz", "https://"):
            self.assertNotIn(secret, output)
        for event in ("publish_ok", "publish_failed", "publish_batch", "threads_container_created"):
            self.assertIn(event, output)
