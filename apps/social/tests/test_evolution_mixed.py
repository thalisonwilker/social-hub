from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.images import sanitize_image
from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services import publishing

from .evolution_helpers import EVOLUTION_SETTINGS, make_whatsapp_account
from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_evolution_publisher import REAUTH, err, evolution_mocks
from .test_threads_publisher import PERMALINK, threads_mocks
from .threads_helpers import THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status
NEW = "social:post_new"
TEXT = "Promo ☀️ para todos"


@override_settings(**{**THREADS_SETTINGS, **EVOLUTION_SETTINGS})
class MixedDestinationsTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.page = self.make_accounts(1)[0]
        self.profile = make_threads_account(self.alice, "900", username="maria")
        self.wa = make_whatsapp_account(self.alice, "loja", name="Loja do centro")

    def make_pub(self, accounts=None, *, image=True, text=TEXT):
        accounts = accounts if accounts is not None else [self.page, self.profile, self.wa]
        return publishing.create_publication(self.alice, text, sanitize_image(make_upload()) if image else None, accounts)

    def statuses(self, pub):
        return {t.platform: t.status for t in pub.targets.all()}

    # ---- AC-10 ------------------------------------------------------------
    def test_AC_10_each_target_goes_to_its_own_platform_and_has_its_own_result(self):
        """AC-10: Facebook, Threads e WhatsApp numa publicação; cada alvo é despachado à sua plataforma e publica."""
        pub = self.make_pub()
        with threads_mocks() as threads, evolution_mocks() as evo:
            result = publishing.send_pending(pub)
        self.assertEqual((result.attempted, result.published, result.failed), (3, 3, 0))
        self.assertEqual(self.publish.call_count, 1)
        threads["create_image_container"].assert_called_once()
        evo["send_status_image"].assert_called_once()
        self.assertEqual(self.statuses(pub), {"facebook_page": S.PUBLISHED, "threads": S.PUBLISHED, "whatsapp_status": S.PUBLISHED})
        self.assertEqual(pub.status, Publication.Status.PUBLISHED)
        wa = pub.targets.get(platform="whatsapp_status")
        self.assertEqual((wa.external_post_id, wa.permalink), ("MSG-I", ""))

    def test_AC_10_a_failing_whatsapp_target_does_not_block_the_others(self):
        """AC-10: a Evolution falha; Facebook e Threads publicam; o status geral é "Com falhas"."""
        pub = self.make_pub()
        with threads_mocks(), evolution_mocks(image=err("timeout")):
            result = publishing.send_pending(pub)
        self.assertEqual((result.published, result.failed), (2, 1))
        self.assertEqual(self.statuses(pub), {"facebook_page": S.PUBLISHED, "threads": S.PUBLISHED, "whatsapp_status": S.FAILED})
        self.assertEqual(pub.status, Publication.Status.FAILED)

    def test_AC_10_failing_facebook_and_threads_do_not_block_whatsapp(self):
        """AC-10: Facebook e Threads falham; o WhatsApp publica mesmo assim."""
        from apps.social.services.meta import MetaApiError

        self.publish.side_effect = MetaApiError("x", code=1, status=500)
        pub = self.make_pub()
        with threads_mocks() as threads, evolution_mocks() as evo:
            threads["create_image_container"].side_effect = MetaApiError("x", code=2, status=500)
            result = publishing.send_pending(pub)
        self.assertEqual((result.published, result.failed), (1, 2))
        self.assertEqual(self.statuses(pub)["whatsapp_status"], S.PUBLISHED)
        evo["send_status_image"].assert_called_once()

    def test_AC_10_try_again_resends_only_failed_targets_and_never_published_ones(self):
        """AC-10: "Tentar novamente" reenvia só o alvo `failed`; os `published` não são tocados."""
        pub = self.make_pub()
        with threads_mocks(), evolution_mocks(image=err("timeout")):
            publishing.send_pending(pub)
        self.publish.reset_mock()
        with threads_mocks() as threads, evolution_mocks() as evo:
            result = publishing.send_pending(pub)
        self.assertEqual((result.attempted, result.published, result.failed), (1, 1, 0))
        self.publish.assert_not_called()
        threads["create_image_container"].assert_not_called()
        evo["send_status_image"].assert_called_once()
        self.assertEqual(pub.status, Publication.Status.PUBLISHED)

    def test_AC_10_account_in_reauth_fails_alone_and_the_others_publish(self):
        """AC-10: conta de WhatsApp em reconexão falha com "Reconecte…" sem chamar a Evolution; os demais publicam."""
        pub = self.make_pub()
        SocialAccount.objects.filter(pk=self.wa.pk).update(status=SocialAccount.Status.NEEDS_REAUTH)
        with threads_mocks(), evolution_mocks() as evo:
            publishing.send_pending(pub)
        for mock_ in evo.values():
            mock_.assert_not_called()
        wa = pub.targets.get(platform="whatsapp_status")
        self.assertEqual((wa.status, wa.error_message), (S.FAILED, REAUTH))
        self.assertEqual(self.statuses(pub)["threads"], S.PUBLISHED)

    def test_AC_10_the_form_flow_publishes_the_three_platforms_and_reports_the_batch(self):
        """AC-10: pelo formulário, Facebook + Threads + WhatsApp publicam e a mensagem resume o lote."""
        with threads_mocks(), evolution_mocks():
            response = self.client.post(
                reverse(NEW), {"text": TEXT, "accounts": [self.page.pk, self.profile.pk, self.wa.pk], "image": make_upload()}, follow=True
            )
        self.assertContains(response, "Publicado em 3 Páginas")
        self.assertContains(response, "Status do WhatsApp")
        self.assertContains(response, PERMALINK)

    def test_AC_10_batch_ceiling_still_applies_across_platforms(self):
        """AC-10: PUBLISH_BATCH_SIZE continua sendo o teto por requisição, qualquer que seja a plataforma."""
        pub = self.make_pub()
        with threads_mocks(), evolution_mocks():
            result = publishing.send_pending(pub, batch_size=2)
        self.assertEqual((result.attempted, result.remaining), (2, 1))

    # ---- AC-15 ------------------------------------------------------------
    def detail(self, pub):
        return self.client.get(reverse("social:post_detail", args=[pub.pk]))

    def test_AC_15_detail_shows_the_whatsapp_target_with_instance_and_no_link(self):
        """AC-15: o detalhe mostra "Status do WhatsApp", a instância e "link indisponível"; sem botão "Ver post" para ele."""
        pub = self.make_pub([self.wa], image=False)
        with evolution_mocks():
            publishing.send_pending(pub)
        response = self.detail(pub)
        self.assertContains(response, "Loja do centro")
        self.assertContains(response, "Status do WhatsApp")
        self.assertContains(response, "instância loja")
        self.assertContains(response, "link indisponível")
        self.assertContains(response, "Publicado")
        self.assertNotContains(response, "Ver post")
        self.assertNotContains(response, "access_token")

    def test_AC_15_detail_shows_the_failure_and_offers_to_try_again(self):
        """AC-15: alvo do WhatsApp que falhou mostra a mensagem amigável e o botão "Tentar novamente"."""
        pub = self.make_pub([self.wa], image=False)
        with evolution_mocks(text=err("timeout")):
            publishing.send_pending(pub)
        response = self.detail(pub)
        self.assertContains(response, "Falha de comunicação com a Evolution.")
        self.assertContains(response, "Tentar novamente")

    def test_AC_15_text_only_publication_keeps_the_icon_instead_of_the_image(self):
        """AC-15: publicação só de texto continua mostrando o ícone; a rota da imagem responde 404."""
        pub = self.make_pub([self.wa], image=False)
        self.assertContains(self.detail(pub), "Publicação só de texto")
        self.assertNotContains(self.detail(pub), reverse("social:post_image", args=[pub.pk]))
        self.assertNotContains(self.client.get(reverse("social:posts")), reverse("social:post_image", args=[pub.pk]))
        self.assertEqual(self.client.get(reverse("social:post_image", args=[pub.pk])).status_code, 404)

    def test_AC_15_history_lists_whatsapp_publications_with_their_counts(self):
        """AC-15: o histórico lista a publicação com as contagens e a descrição das três plataformas."""
        pub = self.make_pub()
        with threads_mocks(), evolution_mocks(image=err("timeout")):
            publishing.send_pending(pub)
        response = self.client.get(reverse("social:posts"))
        self.assertContains(response, "2 publicada(s)")
        self.assertContains(response, "1 com falha")
        self.assertContains(response, "Status no WhatsApp")

    def test_AC_15_history_survives_disconnecting_the_whatsapp_account(self):
        """AC-15: desconectada a conta, o histórico mantém o nome da instância (snapshot) e o alvo deixa de ser reenviável."""
        pub = self.make_pub([self.wa], image=False)
        with evolution_mocks():
            publishing.send_pending(pub)
        self.client.post(reverse("social:account_disconnect", args=[self.wa.pk]))
        response = self.detail(pub)
        self.assertContains(response, "Loja do centro")
        self.assertContains(response, "instância loja")
        self.assertFalse(pub.targets.get().is_retryable)

    def test_AC_15_other_users_cannot_open_the_publication(self):
        """AC-15/AC-16: a publicação do WhatsApp é visível só ao dono."""
        pub = self.make_pub([self.wa], image=False)
        self.client.force_login(self.bob)
        self.assertEqual(self.detail(pub).status_code, 404)


class SpecsUpdatedTests(TestCase):
    def read(self, folder):
        return (settings.BASE_DIR / "specs" / folder / "spec.md").read_text(encoding="utf-8")

    def section(self, spec, start, end):
        return spec[spec.index(start):spec.index(end)]

    def test_AC_10_specs_0003_and_0004_record_that_whatsapp_is_also_a_destination(self):
        """AC-10: as specs 0003 (AC-1, AC-5) e 0004 (AC-13, AC-14) registram a mudança da 0006 (WhatsApp como destino)."""
        s3, s4 = self.read("0003-publicar-no-facebook"), self.read("0004-threads-conectar-e-publicar")
        sections = {
            "0003 AC-1": self.section(s3, "### AC-1:", "### AC-2:"),
            "0003 AC-5": self.section(s3, "### AC-5:", "### AC-6:"),
            "0004 AC-13": self.section(s4, "### AC-13:", "### AC-14:"),
            "0004 AC-14": self.section(s4, "### AC-14:", "### AC-15:"),
        }
        for name, text in sections.items():
            with self.subTest(name):
                self.assertIn("0006", text)
                self.assertIn("WhatsApp", text)
