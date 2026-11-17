"""Views da publicação em segundo plano (spec 0007): enfileirar (AC-1), tentar novamente (AC-5), resolver (AC-9, AC-10),
estado para polling (AC-12) e isolamento/segurança (AC-17)."""
import json
import logging
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.social.images import sanitize_image
from apps.social.models import Publication, PublicationTarget, SocialAccount, WorkerHeartbeat
from apps.social.services import publishing

from .evolution_helpers import EVOLUTION_SETTINGS, make_whatsapp_account
from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_evolution_publisher import evolution_mocks
from .test_threads_publisher import threads_mocks
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status
NEW = "social:post_new"
TEXT = "Texto confidencial da publicação"


@override_settings(**{**THREADS_SETTINGS, **EVOLUTION_SETTINGS}, PUBLISH_MODE="worker")
class BackgroundViewsBase(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.page = self.make_accounts(1)[0]
        self.profile = make_threads_account(self.alice, "900", username="maria")
        self.wa = make_whatsapp_account(self.alice, "loja", key="chave-da-loja")

    def make_pub(self, accounts=None, *, image=True, owner=None):
        accounts = accounts if accounts is not None else [self.page]
        return publishing.create_publication(owner or self.alice, TEXT, sanitize_image(make_upload()) if image else None, accounts)

    def set_status(self, pub, status, **fields):
        PublicationTarget.objects.filter(pk=pub.targets.first().pk).update(status=status, **fields)
        return pub.targets.first()

    def target(self, pub):
        return pub.targets.first()


class EnqueueTests(BackgroundViewsBase):
    # ---- AC-1 --------------------------------------------------------------
    def test_AC_1_publishing_only_enqueues_and_redirects_without_calling_any_platform(self):
        """AC-1: modo worker: cria a publicação e os alvos `pending`, redireciona ao detalhe com a mensagem e NÃO chama plataforma."""
        data = {"text": TEXT, "accounts": [self.page.pk, self.profile.pk, self.wa.pk], "image": make_upload()}
        with mock.patch.object(publishing, "send_pending") as send, threads_mocks() as threads, evolution_mocks() as evo:
            response = self.client.post(reverse(NEW), data)
        pub = Publication.objects.get()
        self.assertRedirects(response, reverse("social:post_detail", args=[pub.pk]), fetch_redirect_response=False)
        self.assertEqual(sorted(t.status for t in pub.targets.all()), [S.PENDING] * 3)
        send.assert_not_called()
        self.publish.assert_not_called()
        for mocked in (*threads.values(), *evo.values()):
            mocked.assert_not_called()
        follow = self.client.get(response["Location"])
        self.assertContains(follow, "Publicação enfileirada: o envio acontece em segundo plano.")

    def test_AC_1_form_validations_and_security_still_apply(self):
        """AC-1: as regras do formulário (imagem obrigatória com Facebook, texto, destinos) seguem valendo; nada é criado nem enfileirado."""
        cases = [
            {"text": TEXT, "accounts": [self.page.pk]},  # Facebook sem imagem
            {"text": "   ", "accounts": [self.wa.pk]},
            {"text": TEXT, "accounts": []},
            {"text": TEXT, "accounts": ["99999"]},
        ]
        for data in cases:
            with self.subTest(accounts=data["accounts"]):
                response = self.client.post(reverse(NEW), data)
                self.assertEqual(response.status_code, 200)
        self.assertEqual((Publication.objects.count(), PublicationTarget.objects.count()), (0, 0))

    def test_AC_1_the_enqueued_publication_is_sent_later_by_the_worker(self):
        """AC-1: o que foi enfileirado depois é enviado pelo worker (ponta a ponta: view → fila → worker)."""
        from apps.social.services.worker import Worker

        self.client.post(reverse(NEW), {"text": TEXT, "accounts": [self.page.pk], "image": make_upload()})
        self.assertEqual(Publication.objects.get().targets.get().status, S.PENDING)
        Worker(pid=1).run_once()
        self.assertEqual(Publication.objects.get().targets.get().status, S.PUBLISHED)

    @override_settings(PUBLISH_MODE="inline")
    def test_AC_2_inline_mode_still_sends_in_the_request(self):
        """AC-2: modo inline: Publicar envia na requisição (como nas 0003–0006)."""
        self.client.post(reverse(NEW), {"text": TEXT, "accounts": [self.page.pk], "image": make_upload()}, follow=True)
        self.assertEqual(Publication.objects.get().targets.get().status, S.PUBLISHED)
        self.publish.assert_called_once()


class TryAgainTests(BackgroundViewsBase):
    # ---- AC-5 --------------------------------------------------------------
    def test_AC_5_try_again_requeues_failed_targets_and_sends_nothing_in_the_request(self):
        """AC-5: modo worker: "Tentar novamente" faz `failed → pending` (só com conta), mostra "Reenvio enfileirado" e nada é enviado."""
        pub = self.make_pub([self.page, self.profile, self.wa])
        failed, published, uncertain = list(pub.targets.all())
        PublicationTarget.objects.filter(pk=failed.pk).update(status=S.FAILED, error_message="x", error_code="y")
        PublicationTarget.objects.filter(pk=published.pk).update(status=S.PUBLISHED)
        PublicationTarget.objects.filter(pk=uncertain.pk).update(status=S.UNCERTAIN)
        with mock.patch.object(publishing, "send_pending") as send:
            response = self.client.post(reverse("social:post_send", args=[pub.pk]), follow=True)
        send.assert_not_called()
        self.publish.assert_not_called()
        self.assertContains(response, "Reenvio enfileirado")
        self.assertEqual({t.pk: t.status for t in pub.targets.all()}, {failed.pk: S.PENDING, published.pk: S.PUBLISHED, uncertain.pk: S.UNCERTAIN})
        self.assertEqual(PublicationTarget.objects.get(pk=failed.pk).error_message, "")

    def test_AC_5_try_again_without_failed_targets_changes_nothing(self):
        """AC-5: sem `failed` reenfileirável a tela avisa e nenhum estado muda (inclusive `failed` sem conta)."""
        pub = self.make_pub([self.page, self.profile])
        orphan, ok = list(pub.targets.all())
        PublicationTarget.objects.filter(pk=orphan.pk).update(status=S.FAILED, account=None)
        PublicationTarget.objects.filter(pk=ok.pk).update(status=S.PUBLISHED)
        response = self.client.post(reverse("social:post_send", args=[pub.pk]), follow=True)
        self.assertContains(response, "Nada a reenviar")
        self.assertEqual({t.pk: t.status for t in pub.targets.all()}, {orphan.pk: S.FAILED, ok.pk: S.PUBLISHED})

    def test_AC_5_a_second_click_does_not_requeue_again_or_duplicate_anything(self):
        """AC-5: o segundo clique encontra o alvo já `pending` e não faz nada; o worker o envia uma única vez."""
        from apps.social.services.worker import Worker

        pub = self.make_pub([self.page])
        self.set_status(pub, S.FAILED)
        url = reverse("social:post_send", args=[pub.pk])
        self.client.post(url)
        second = self.client.post(url, follow=True)
        self.assertContains(second, "Nada a reenviar")
        Worker(pid=1).run_once()
        Worker(pid=1).run_once()
        self.assertEqual(self.publish.call_count, 1)

    @override_settings(PUBLISH_MODE="inline")
    def test_AC_5_inline_mode_sends_failed_targets_in_the_request(self):
        """AC-5/AC-2: modo inline: "Tentar novamente" reenfileira e envia na requisição, como antes."""
        pub = self.make_pub([self.page])
        self.set_status(pub, S.FAILED)
        self.client.post(reverse("social:post_send", args=[pub.pk]))
        self.assertEqual(self.target(pub).status, S.PUBLISHED)


class ResolveTests(BackgroundViewsBase):
    def resolve(self, pub, action, target=None, **kw):
        target = target or self.target(pub)
        return self.client.post(reverse("social:target_resolve", args=[pub.pk, target.pk]), {"acao": action}, **kw)

    # ---- AC-9 --------------------------------------------------------------
    def test_AC_9_already_published_marks_it_published_without_link_and_logs_only_the_action(self):
        """AC-9: "Já foi publicado": `uncertain → published`, sem link nem id, erro limpo, `published_at` agora."""
        pub = self.make_pub([self.page])
        self.set_status(pub, S.UNCERTAIN, error_message=publishing.MSG_UNCERTAIN, error_code="timeout")
        with self.assertLogs("apps.social.meta", level=logging.INFO) as logs:
            response = self.resolve(pub, "publicado", follow=True)
        target = self.target(pub)
        self.assertEqual((target.status, target.permalink, target.external_post_id, target.error_message, target.error_code),
                         (S.PUBLISHED, "", "", "", ""))
        self.assertIsNotNone(target.published_at)
        self.assertContains(response, "Marcado como já publicado.")
        self.assertContains(response, "link indisponível")
        self.assertIn("target_resolved action=published", "\n".join(logs.output))
        self.assertNotIn(TEXT, "\n".join(logs.output))
        self.publish.assert_not_called()

    def test_AC_9_works_even_without_an_account(self):
        """AC-9: conta desconectada: ainda dá para marcar como já publicado."""
        pub = self.make_pub([self.page])
        self.set_status(pub, S.UNCERTAIN, account=None)
        self.resolve(pub, "publicado")
        self.assertEqual(self.target(pub).status, S.PUBLISHED)

    def test_AC_9_any_other_state_is_refused_and_nothing_changes(self):
        """AC-9: só `uncertain` é resolvível; pending/sending/failed/published recusam e nada muda."""
        for status in (S.PENDING, S.SENDING, S.FAILED, S.PUBLISHED):
            with self.subTest(status=status):
                pub = self.make_pub([self.page])
                self.set_status(pub, status)
                response = self.resolve(pub, "publicado", follow=True)
                self.assertContains(response, "Este alvo não está incerto")
                self.assertEqual(self.target(pub).status, status)

    def test_AC_9_unknown_action_changes_nothing(self):
        """AC-9: ação desconhecida ou ausente: nada é alterado."""
        pub = self.make_pub([self.page])
        self.set_status(pub, S.UNCERTAIN)
        for action in ("", "apagar", "PUBLICADO"):
            with self.subTest(action=action):
                response = self.resolve(pub, action, follow=True)
                self.assertContains(response, "Ação desconhecida")
                self.assertEqual(self.target(pub).status, S.UNCERTAIN)

    # ---- AC-10 -------------------------------------------------------------
    def test_AC_10_resend_requeues_the_uncertain_target_and_the_worker_sends_it(self):
        """AC-10: "Reenviar": `uncertain → pending` (nada enviado na requisição); o worker o envia depois."""
        from apps.social.services.worker import Worker

        pub = self.make_pub([self.page])
        self.set_status(pub, S.UNCERTAIN, error_message=publishing.MSG_UNCERTAIN, error_code="interrupted")
        with self.assertLogs("apps.social.meta", level=logging.INFO) as logs:
            response = self.resolve(pub, "reenviar", follow=True)
        self.assertContains(response, "Reenvio enfileirado")
        self.publish.assert_not_called()
        target = self.target(pub)
        self.assertEqual((target.status, target.error_message, target.error_code), (S.PENDING, "", ""))
        self.assertIn("target_resolved action=resend", "\n".join(logs.output))
        Worker(pid=1).run_once()
        self.assertEqual(self.target(pub).status, S.PUBLISHED)

    def test_AC_10_resend_without_an_account_is_refused(self):
        """AC-10: sem conta não dá para reenviar (mensagem clara) e o alvo continua Incerto."""
        pub = self.make_pub([self.page])
        self.set_status(pub, S.UNCERTAIN, account=None)
        response = self.resolve(pub, "reenviar", follow=True)
        self.assertContains(response, "não tem conta conectada")
        self.assertEqual(self.target(pub).status, S.UNCERTAIN)

    def test_AC_10_resend_of_other_states_is_refused(self):
        """AC-10: estados diferentes de `uncertain` são recusados."""
        for status in (S.PENDING, S.SENDING, S.FAILED, S.PUBLISHED):
            with self.subTest(status=status):
                pub = self.make_pub([self.page])
                self.set_status(pub, status)
                self.resolve(pub, "reenviar")
                self.assertEqual(self.target(pub).status, status)

    def test_AC_10_double_submit_resends_only_once(self):
        """AC-10: duplo clique em "Reenviar": só o primeiro vale; o segundo é recusado."""
        pub = self.make_pub([self.page])
        self.set_status(pub, S.UNCERTAIN)
        self.resolve(pub, "reenviar")
        second = self.resolve(pub, "reenviar", follow=True)
        self.assertContains(second, "Este alvo não está incerto")
        self.assertEqual(self.target(pub).status, S.PENDING)

    @override_settings(PUBLISH_MODE="inline")
    def test_AC_10_inline_mode_resend_sends_in_the_request(self):
        """AC-10/AC-2: modo inline: "Reenviar" envia na requisição."""
        pub = self.make_pub([self.page])
        self.set_status(pub, S.UNCERTAIN)
        self.resolve(pub, "reenviar")
        self.assertEqual(self.target(pub).status, S.PUBLISHED)

    def test_AC_10_resend_of_a_whatsapp_target_goes_through_the_worker_with_the_account_key(self):
        """AC-10: o reenvio do Status usa a chave da conta e só acontece no worker."""
        from apps.social.services.worker import Worker

        pub = self.make_pub([self.wa], image=False)
        self.set_status(pub, S.UNCERTAIN)
        self.resolve(pub, "reenviar")
        with evolution_mocks() as evo:
            Worker(pid=1).run_once()
        self.assertEqual(evo["send_status_text"].call_args.args[:2], ("loja", "chave-da-loja"))


class StateEndpointTests(BackgroundViewsBase):
    def state(self, pub, **kw):
        return self.client.get(reverse("social:post_state", args=[pub.pk]), **kw)

    # ---- AC-12 -------------------------------------------------------------
    def test_AC_12_state_json_has_only_the_minimal_fields(self):
        """AC-12: JSON com `status`, `counts`, `targets` (id/status), `worker.active` e `done`; sem texto, contas, mensagens nem URLs."""
        pub = self.make_pub([self.page, self.profile, self.wa])
        PublicationTarget.objects.filter(pk=pub.targets.first().pk).update(status=S.FAILED, error_message="Mensagem de erro específica")
        response = self.state(pub)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response["Cache-Control"], "no-store")
        data = response.json()
        self.assertEqual(set(data), {"status", "counts", "targets", "worker", "done"})
        self.assertEqual(set(data["worker"]), {"active"})
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["counts"]["pending"], 2)
        self.assertEqual(data["counts"]["failed"], 1)
        self.assertEqual(len(data["targets"]), 3)
        for item in data["targets"]:
            self.assertEqual(set(item), {"id", "status"})
        raw = response.content.decode()
        for leak in (TEXT, "Mensagem de erro específica", "maria", "loja", "Página 1", "http", "chave"):
            self.assertNotIn(leak, raw)

    def test_AC_12_done_is_true_only_when_nothing_is_pending_or_sending(self):
        """AC-12: `done` fica `false` com alvo `pending`/`sending` e `true` quando todos terminaram (published/failed/uncertain)."""
        pub = self.make_pub([self.page, self.profile])
        first, second = list(pub.targets.all())
        self.assertFalse(self.state(pub).json()["done"])
        PublicationTarget.objects.filter(pk=first.pk).update(status=S.SENDING)
        self.assertFalse(self.state(pub).json()["done"])
        PublicationTarget.objects.filter(pk=first.pk).update(status=S.UNCERTAIN)
        PublicationTarget.objects.filter(pk=second.pk).update(status=S.PUBLISHED)
        data = self.state(pub).json()
        self.assertTrue(data["done"])
        self.assertEqual(data["status"], "uncertain")
        PublicationTarget.objects.filter(pk=first.pk).update(status=S.FAILED)
        self.assertTrue(self.state(pub).json()["done"])

    @override_settings(WORKER_HEARTBEAT_STALE_SECONDS=180)
    def test_AC_12_worker_active_follows_the_heartbeat(self):
        """AC-12: `worker.active` reflete o heartbeat (ausente/vencido = false; recente = true)."""
        pub = self.make_pub()
        self.assertFalse(self.state(pub).json()["worker"]["active"])
        WorkerHeartbeat.beat(pid=1)
        self.assertTrue(self.state(pub).json()["worker"]["active"])
        WorkerHeartbeat.objects.update(beat_at=timezone.now() - timezone.timedelta(seconds=181))
        self.assertFalse(self.state(pub).json()["worker"]["active"])

    def test_AC_12_only_get_is_accepted(self):
        """AC-12: o endpoint só aceita GET (POST/PUT/DELETE → 405)."""
        pub = self.make_pub()
        url = reverse("social:post_state", args=[pub.pk])
        for method in ("post", "put", "delete", "patch"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(url).status_code, 405)

    def test_AC_12_other_users_get_404(self):
        """AC-12: a publicação de outro usuário responde 404."""
        pub = self.make_pub()
        self.client.force_login(self.bob)
        self.assertEqual(self.state(pub).status_code, 404)


class SecurityTests(BackgroundViewsBase):
    # ---- AC-17 -------------------------------------------------------------
    def urls_for(self, pub):
        target = pub.targets.first()
        return {
            "estado": reverse("social:post_state", args=[pub.pk]),
            "enviar": reverse("social:post_send", args=[pub.pk]),
            "resolver": reverse("social:target_resolve", args=[pub.pk, target.pk]),
        }

    def test_AC_17_other_users_cannot_state_retry_or_resolve(self):
        """AC-17: estado, "Tentar novamente" e resolver só funcionam nas publicações do próprio usuário (404 nas dos outros; nada muda)."""
        pub = self.make_pub()
        self.set_status(pub, S.UNCERTAIN)
        self.client.force_login(self.bob)
        urls = self.urls_for(pub)
        self.assertEqual(self.client.get(urls["estado"]).status_code, 404)
        self.assertEqual(self.client.post(urls["enviar"]).status_code, 404)
        for action in ("publicado", "reenviar"):
            self.assertEqual(self.client.post(urls["resolver"], {"acao": action}).status_code, 404)
        self.assertEqual(self.target(pub).status, S.UNCERTAIN)

    def test_AC_17_a_target_id_from_another_publication_is_404(self):
        """AC-17: trocar o id do alvo por um de outra publicação (mesmo dono) dá 404 e nada muda."""
        mine, other = self.make_pub(), self.make_pub()
        self.set_status(other, S.UNCERTAIN)
        url = reverse("social:target_resolve", args=[mine.pk, other.targets.first().pk])
        self.assertEqual(self.client.post(url, {"acao": "publicado"}).status_code, 404)
        self.assertEqual(self.target(other).status, S.UNCERTAIN)

    def test_AC_17_resolve_needs_post_csrf_and_login(self):
        """AC-17: resolver exige POST (GET → 405), CSRF (sem token → 403) e login (anônimo → redireciona)."""
        pub = self.make_pub()
        self.set_status(pub, S.UNCERTAIN)
        url = self.urls_for(pub)["resolver"]
        self.assertEqual(self.client.get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.alice)
        self.assertEqual(strict.post(url, {"acao": "publicado"}).status_code, 403)
        anonymous = Client()
        response = anonymous.post(url, {"acao": "publicado"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/entrar/", response["Location"])
        self.assertEqual(self.target(pub).status, S.UNCERTAIN)

    def test_AC_17_retry_needs_post_csrf_and_login(self):
        """AC-17: "Tentar novamente" exige POST, CSRF e login."""
        pub = self.make_pub()
        self.set_status(pub, S.FAILED)
        url = self.urls_for(pub)["enviar"]
        self.assertEqual(self.client.get(url).status_code, 405)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.alice)
        self.assertEqual(strict.post(url).status_code, 403)
        self.assertEqual(Client().post(url).status_code, 302)
        self.assertEqual(self.target(pub).status, S.FAILED)

    def test_AC_17_state_endpoint_requires_login(self):
        """AC-17: o endpoint de estado exige login (anônimo → redireciona para a entrada)."""
        pub = self.make_pub()
        response = Client().get(self.urls_for(pub)["estado"])
        self.assertEqual(response.status_code, 302)
        self.assertIn("/entrar/", response["Location"])

    def test_AC_17_new_logs_never_carry_text_keys_or_message_bodies(self):
        """AC-17: nenhum log novo (enfileirar, reenfileirar, resolver) traz texto, chave ou nome de conta."""
        pub = self.make_pub([self.wa], image=False)
        self.set_status(pub, S.UNCERTAIN)
        with self.assertLogs(level=logging.DEBUG) as logs:
            logging.getLogger("apps.social.meta").debug("sentinela")
            self.client.post(self.urls_for(pub)["resolver"], {"acao": "reenviar"})
            self.client.post(self.urls_for(pub)["enviar"])
            self.client.get(self.urls_for(pub)["estado"])
        output = "\n".join(logs.output)
        for secret in (TEXT, "chave-da-loja", "loja"):
            self.assertNotIn(secret, output)
