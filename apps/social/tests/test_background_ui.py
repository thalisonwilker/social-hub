"""Tela da publicação em segundo plano (spec 0007): estados e contagens (AC-11), polling (AC-13), aviso de worker inativo (AC-14)."""
import shutil
import subprocess
import unittest
from datetime import timedelta

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.social.images import sanitize_image
from apps.social.models import PublicationTarget, SocialAccount, WorkerHeartbeat
from apps.social.services import publishing

from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status
WARNING = "O envio em segundo plano não está ativo: os envios ficam na fila até o worker voltar."


@override_settings(**THREADS_SETTINGS, PUBLISH_MODE="worker", WORKER_HEARTBEAT_STALE_SECONDS=180)
class BackgroundUiTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.page = self.make_accounts(1)[0]
        self.profile = make_threads_account(self.alice, "900", username="maria")

    def make_pub(self, statuses, accounts=None):
        accounts = accounts or [self.page, self.profile][: len(statuses)]
        pub = publishing.create_publication(self.alice, "Texto", sanitize_image(make_upload()), accounts)
        for target, status in zip(pub.targets.order_by("id"), statuses):
            PublicationTarget.objects.filter(pk=target.pk).update(status=status)
        return pub

    def detail(self, pub):
        return self.client.get(reverse("social:post_detail", args=[pub.pk]))

    # ---- AC-11 -------------------------------------------------------------
    def test_AC_11_detail_and_history_show_the_uncertain_count_and_the_general_label(self):
        """AC-11: detalhe e histórico mostram "N incerto(s)" e o rótulo geral "Incerta"."""
        pub = self.make_pub([S.UNCERTAIN, S.PUBLISHED])
        detail = self.detail(pub)
        self.assertContains(detail, "1 incerto(s)")
        self.assertContains(detail, "Incerta")
        history = self.client.get(reverse("social:posts"))
        self.assertContains(history, "1 incerto(s)")
        self.assertContains(history, "Incerta")

    def test_AC_11_failed_keeps_precedence_over_uncertain_in_the_label(self):
        """AC-11: com falha e incerto juntos o rótulo geral é "Com falhas"; as duas contagens aparecem."""
        pub = self.make_pub([S.FAILED, S.UNCERTAIN])
        detail = self.detail(pub)
        self.assertContains(detail, "Com falhas")
        self.assertContains(detail, "1 com falha")
        self.assertContains(detail, "1 incerto(s)")

    def test_AC_11_the_uncertain_target_shows_its_message_and_the_two_resolve_buttons(self):
        """AC-11: o alvo Incerto mostra a mensagem e as duas ações (formulários POST com CSRF e confirmação)."""
        pub = self.make_pub([S.UNCERTAIN])
        PublicationTarget.objects.update(error_message=publishing.MSG_UNCERTAIN, error_code="timeout")
        target = pub.targets.get()
        response = self.detail(pub)
        action = reverse("social:target_resolve", args=[pub.pk, target.pk])
        html = response.content.decode()
        self.assertContains(response, publishing.MSG_UNCERTAIN)
        self.assertEqual(html.count(f'action="{action}"'), 2)
        self.assertContains(response, 'name="acao" value="publicado"')
        self.assertContains(response, 'name="acao" value="reenviar"')
        self.assertContains(response, "Já foi publicado")
        self.assertContains(response, "Reenviar")
        self.assertContains(response, "Reenviar pode duplicar o post na plataforma. Continuar?")
        self.assertContains(response, "csrfmiddlewaretoken", count=5)  # 2 formulários + sair + 2 "Remover do Hub" (spec 0010)
        self.assertNotIn('disabled aria-disabled="true" title="Sem conta', html)

    def test_AC_11_resend_is_disabled_without_an_account_but_already_published_is_not(self):
        """AC-11: sem conta, "Reenviar" fica desabilitado (com a explicação) e "Já foi publicado" continua disponível."""
        pub = self.make_pub([S.UNCERTAIN])
        PublicationTarget.objects.update(account=None)
        html = self.detail(pub).content.decode()
        self.assertIn("Sem conta conectada: só dá para marcar como já publicado", html)
        publicado = html.split('name="acao" value="publicado"')[1].split("</form>")[0]
        reenviar = html.split('name="acao" value="reenviar"')[1].split("</form>")[0]
        self.assertNotIn("disabled", publicado)
        self.assertIn("disabled", reenviar)

    def test_AC_11_only_uncertain_targets_get_resolve_buttons(self):
        """AC-11: alvos em outros estados não têm os botões do Incerto."""
        pub = self.make_pub([S.PUBLISHED, S.FAILED])
        self.assertNotContains(self.detail(pub), 'name="acao"')

    # ---- AC-13 -------------------------------------------------------------
    def test_AC_13_pending_and_sending_targets_are_shown_as_in_the_queue_and_sending(self):
        """AC-13: modo worker: `pending` aparece como "Na fila" e `sending` como "Enviando…"."""
        pub = self.make_pub([S.PENDING, S.SENDING])
        response = self.detail(pub)
        self.assertContains(response, "Na fila")
        self.assertContains(response, "Enviando…")
        self.assertNotContains(response, "Aguardando envio")

    @override_settings(PUBLISH_MODE="inline")
    def test_AC_13_inline_mode_keeps_the_old_wording_for_pending(self):
        """AC-13/AC-2: modo inline mantém "Aguardando envio" para `pending`."""
        self.assertContains(self.detail(self.make_pub([S.PENDING])), "Aguardando envio")

    def test_AC_13_polling_attributes_are_rendered_only_while_something_is_in_progress(self):
        """AC-13: com alvo `pending`/`sending` a página traz a URL de estado, a assinatura e o intervalo de 3 s; terminada, não traz nada."""
        pub = self.make_pub([S.PENDING, S.PUBLISHED])
        html = self.detail(pub).content.decode()
        self.assertIn(f'data-poll-url="{reverse("social:post_state", args=[pub.pk])}"', html)
        self.assertIn('data-poll-interval="3000"', html)
        sending = self.make_pub([S.SENDING])
        self.assertIn("data-poll-url", self.detail(sending).content.decode())
        for statuses in ([S.PUBLISHED, S.PUBLISHED], [S.FAILED, S.UNCERTAIN], [S.UNCERTAIN]):
            with self.subTest(statuses=[str(s) for s in statuses]):
                self.assertNotIn("data-poll", self.detail(self.make_pub(statuses)).content.decode())

    def test_AC_13_the_page_signature_matches_the_one_the_script_builds_from_the_state_json(self):
        """AC-13: `data-poll-signature` (servidor) == assinatura que o JS calcula do JSON de estado ("id:estado|id:estado")."""
        pub = self.make_pub([S.PENDING, S.SENDING])
        html = self.detail(pub).content.decode()
        state = self.client.get(reverse("social:post_state", args=[pub.pk])).json()
        script_signature = "|".join(f"{t['id']}:{t['status']}" for t in state["targets"])
        self.assertIn(f'data-poll-signature="{script_signature}"', html)

    def test_AC_13_the_polling_script_is_loaded_by_every_page(self):
        """AC-13: o `poll.js` é carregado pelo layout base."""
        html = self.detail(self.make_pub([S.PENDING])).content.decode()
        # em produção o storage com manifesto acrescenta o hash ao nome (js/poll.<hash>.js)
        self.assertRegex(html, r'<script src="[^"]*js/poll(\.[0-9a-f]+)?\.js"></script>')
        source = (settings.BASE_DIR / "static" / "js" / "poll.js").read_text(encoding="utf-8")
        for needle in ("data-poll-url", "data-poll-signature", "location.reload", "done"):
            self.assertIn(needle, source)

    @unittest.skipUnless(shutil.which("node") and (settings.BASE_DIR / "scripts" / "test-poll.mjs").exists(), "node ou scripts/ ausentes (imagem Docker)")
    def test_AC_13_the_polling_logic_passes_its_node_tests(self):
        """AC-13: consulta a cada 3 s, recarrega quando a assinatura muda, para ao terminar, desiste após falhas e respeita aba oculta."""
        result = subprocess.run(
            ["node", str(settings.BASE_DIR / "scripts" / "test-poll.mjs")], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok: polling", result.stdout)

    def test_AC_13_worker_mode_has_no_continue_sending_button_only_try_again_for_failed(self):
        """AC-13/AC-5: modo worker: nunca "Continuar envio"; "Tentar novamente" só com alvo `failed` com conta."""
        pending = self.detail(self.make_pub([S.PENDING]))
        self.assertNotContains(pending, "Continuar envio")
        self.assertNotContains(pending, "Tentar novamente")
        failed = self.detail(self.make_pub([S.FAILED]))
        self.assertContains(failed, "Tentar novamente")
        self.assertNotContains(failed, "Continuar envio")
        uncertain = self.detail(self.make_pub([S.UNCERTAIN]))
        self.assertNotContains(uncertain, "Tentar novamente")

    # ---- AC-14 -------------------------------------------------------------
    def test_AC_14_warns_when_there_is_work_in_progress_and_no_active_worker(self):
        """AC-14: modo worker, alvo `pending`/`sending` e heartbeat ausente → aviso."""
        for status in (S.PENDING, S.SENDING):
            with self.subTest(status=status):
                self.assertContains(self.detail(self.make_pub([status])), WARNING)

    def test_AC_14_warns_when_the_heartbeat_is_stale(self):
        """AC-14: heartbeat vencido (> 180 s) → aviso."""
        WorkerHeartbeat.beat(pid=1)
        WorkerHeartbeat.objects.update(beat_at=timezone.now() - timedelta(seconds=181))
        self.assertContains(self.detail(self.make_pub([S.PENDING])), WARNING)

    def test_AC_14_no_warning_with_a_recent_heartbeat(self):
        """AC-14: heartbeat recente → sem aviso."""
        WorkerHeartbeat.beat(pid=1)
        self.assertNotContains(self.detail(self.make_pub([S.PENDING])), WARNING)

    def test_AC_14_no_warning_when_nothing_is_in_progress(self):
        """AC-14: sem alvo em andamento (publicado/falhou/incerto) não avisa, mesmo sem worker."""
        for statuses in ([S.PUBLISHED], [S.FAILED], [S.UNCERTAIN]):
            with self.subTest(statuses=[str(s) for s in statuses]):
                self.assertNotContains(self.detail(self.make_pub(statuses)), WARNING)

    @override_settings(PUBLISH_MODE="inline")
    def test_AC_14_no_warning_in_inline_mode(self):
        """AC-14: modo inline nunca mostra o aviso."""
        self.assertNotContains(self.detail(self.make_pub([S.PENDING])), WARNING)
