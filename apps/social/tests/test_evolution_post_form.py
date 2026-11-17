from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services.publishing import BatchResult

from .evolution_helpers import EVOLUTION_SETTINGS, make_whatsapp_account
from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .threads_helpers import THREADS_SETTINGS, make_threads_account

NEW = "social:post_new"
WA = SocialAccount.Platform.WHATSAPP_STATUS


@override_settings(**EVOLUTION_SETTINGS, **{k: v for k, v in THREADS_SETTINGS.items() if k != "META_TOKEN_ENCRYPTION_KEY"})
class WhatsAppFormTests(PublicationTestMixin, TestCase):
    """O envio em si é da T5; aqui o despacho é neutralizado para olhar só o formulário."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch("apps.social.views_publications.publishing.send_pending", return_value=BatchResult(0, 0, 0, 0))
        self.send = patcher.start()
        self.addCleanup(patcher.stop)
        self.page = self.make_accounts(1)[0]
        self.profile = make_threads_account(self.alice, "900", username="maria")
        self.wa = make_whatsapp_account(self.alice, "loja", name="Loja do centro")

    def post(self, destinations, text="Olá, mundo", upload=None, no_image=False, **extra):
        data = {"text": text, "accounts": [str(d.pk) if hasattr(d, "pk") else d for d in destinations]}
        if not no_image:
            data["image"] = upload or make_upload()
        data.update(extra)
        return self.client.post(reverse(NEW), data)

    def assertNothingCreated(self):
        self.assertEqual(Publication.objects.count(), 0)
        self.assertEqual(PublicationTarget.objects.count(), 0)
        self.send.assert_not_called()

    # ---- AC-6 ------------------------------------------------------------
    def test_AC_6_whatsapp_group_lists_active_accounts_with_rules(self):
        """AC-6: grupo "Status do WhatsApp" com a conta, "Marcar todas" e a explicação das regras."""
        response = self.client.get(reverse(NEW))
        self.assertContains(response, "Status do WhatsApp")
        self.assertContains(response, "Loja do centro")
        self.assertContains(response, "instância loja")
        self.assertContains(response, 'name="accounts"', count=3)
        self.assertContains(response, "Marcar todas")
        self.assertContains(response, "No WhatsApp, vai como Status")
        self.assertContains(response, "Obrigatória se marcar uma Página do Facebook")

    def test_AC_6_reauth_accounts_are_disabled_with_a_warning_and_guidance(self):
        """AC-6: conta em Reconexão necessária fica desabilitada, com aviso e orientação para reconectar na Evolution."""
        make_whatsapp_account(self.alice, "velha", status=SocialAccount.Status.NEEDS_REAUTH, name="Loja velha")
        response = self.client.get(reverse(NEW))
        self.assertEqual(response.content.decode().count(" disabled"), 1)
        self.assertContains(response, "Reconexão necessária")
        self.assertContains(response, "Loja velha")
        self.assertContains(response, "reconecte o número na Evolution")

    def test_AC_6_other_users_accounts_never_appear(self):
        """AC-6: contas de WhatsApp de outros usuários não aparecem."""
        make_whatsapp_account(self.bob, "do-bob", name="Loja do Bob")
        self.assertNotContains(self.client.get(reverse(NEW)), "Loja do Bob")

    @override_settings(EVOLUTION_API_URL="")
    def test_AC_6_not_configured_makes_whatsapp_unselectable_and_keeps_the_rest(self):
        """AC-6/AC-4: sem EVOLUTION_API_URL a conta aparece desabilitada ("Integração não configurada"); Facebook e Threads seguem."""
        response = self.client.get(reverse(NEW))
        self.assertContains(response, "Integração não configurada")
        self.assertContains(response, 'name="text"')
        response = self.post([self.wa], no_image=True)
        self.assertContains(response, "Seleção de Página inválida")
        self.assertNothingCreated()

    @override_settings(EVOLUTION_API_URL="")
    def test_AC_6_only_whatsapp_accounts_and_not_configured_blocks_with_a_clear_message(self):
        """AC-6/AC-4: com só WhatsApp ativo e a integração desligada, o formulário é bloqueado com mensagem clara."""
        SocialAccount.objects.exclude(pk=self.wa.pk).delete()
        response = self.client.get(reverse(NEW))
        self.assertContains(response, "Integração com o WhatsApp não configurada.")
        self.assertNotContains(response, 'name="text"')

    def test_AC_6_no_active_accounts_message_mentions_whatsapp(self):
        """AC-6: sem nenhuma conta ativa, a mensagem inclui o WhatsApp entre as opções."""
        SocialAccount.objects.all().delete()
        self.assertContains(self.client.get(reverse(NEW)), "número de WhatsApp")

    # ---- AC-7 (matriz do formulário) -----------------------------------------
    def test_AC_7_whatsapp_only_without_image_is_created_without_image(self):
        """AC-7: só WhatsApp, sem imagem → criada sem imagem, alvo pendente `whatsapp_status`, despacho chamado."""
        response = self.post([self.wa], no_image=True)
        pub = Publication.objects.get()
        self.assertRedirects(response, reverse("social:post_detail", args=[pub.pk]), fetch_redirect_response=False)
        self.assertFalse(pub.has_image)
        target = pub.targets.get()
        self.assertEqual((target.platform, target.page_external_id, target.page_name), (WA, "loja", "Loja do centro"))
        self.send.assert_called_once()

    def test_AC_7_whatsapp_only_with_valid_image_stores_the_image(self):
        """AC-7: só WhatsApp com imagem válida → criada com a imagem sanitizada."""
        self.post([self.wa])
        self.assertTrue(Publication.objects.get().has_image)

    def test_AC_7_invalid_image_is_rejected_even_with_only_whatsapp(self):
        """AC-7: imagem enviada e inválida é sempre erro, mesmo sem Facebook; nada criado."""
        fake = SimpleUploadedFile("falsa.jpg", b"nao sou imagem", content_type="image/jpeg")
        response = self.post([self.wa], upload=fake)
        self.assertContains(response, "não é uma imagem válida")
        self.assertNothingCreated()

    def test_AC_7_facebook_plus_whatsapp_requires_an_image(self):
        """AC-7: Facebook + WhatsApp sem imagem → "Escolha uma imagem"; nada criado."""
        self.assertContains(self.post([self.page, self.wa], no_image=True), "Escolha uma imagem")
        self.assertNothingCreated()

    def test_AC_7_all_three_platforms_with_a_valid_image_create_three_targets(self):
        """AC-7: Facebook + Threads + WhatsApp com imagem válida → três alvos, um por plataforma."""
        self.post([self.page, self.profile, self.wa])
        pub = Publication.objects.get()
        self.assertTrue(pub.has_image)
        self.assertEqual(sorted(pub.targets.values_list("platform", flat=True)), ["facebook_page", "threads", "whatsapp_status"])

    def test_AC_7_threads_plus_whatsapp_without_image_keeps_the_threads_text_rules(self):
        """AC-7: Threads + WhatsApp sem imagem: as regras do Threads (500, 5 links) também valem para o texto."""
        self.assertContains(self.post([self.profile, self.wa], text="a" * 501, no_image=True), "No Threads o texto pode ter até 500")
        self.assertNothingCreated()
        self.post([self.profile, self.wa], text="a" * 500, no_image=True)
        self.assertEqual(Publication.objects.get().targets.count(), 2)

    def test_AC_7_whatsapp_has_no_extra_text_limit_beyond_the_general_one(self):
        """AC-7: sem Threads marcado, o limite do WhatsApp é só o geral (5000); 5001 é rejeitado."""
        self.post([self.wa], text="a" * 4000, no_image=True)
        self.assertEqual(Publication.objects.count(), 1)
        self.assertContains(self.post([self.wa], text="a" * 5001, no_image=True), "no máximo 5000")
        self.assertEqual(Publication.objects.count(), 1)

    def test_AC_7_empty_text_is_invalid_for_whatsapp(self):
        """AC-7: texto vazio continua inválido."""
        self.assertContains(self.post([self.wa], text="   ", no_image=True), "Escreva o texto")
        self.assertNothingCreated()

    def test_AC_7_whatsapp_only_does_not_require_the_public_address(self):
        """AC-7: WhatsApp (base64) não exige endereço público, ao contrário do Threads com imagem."""
        with override_settings(PUBLIC_BASE_URL="", THREADS_REDIRECT_URI=""):
            self.post([self.wa])
        self.assertEqual(Publication.objects.count(), 1)

    def test_AC_7_invalid_destination_selection_is_rejected(self):
        """AC-7/AC-16: conta de outro usuário, em reconexão, inexistente ou misturada com válida → erro; nada criado."""
        theirs = make_whatsapp_account(self.bob, "do-bob")
        stale = make_whatsapp_account(self.alice, "velha", status=SocialAccount.Status.NEEDS_REAUTH)
        cases = {
            "de outro usuário": [theirs],
            "em reconexão": [stale],
            "inexistente": ["99999"],
            "válida + de outro": [self.wa, theirs],
            "válida + em reconexão": [self.wa, stale],
        }
        for name, selection in cases.items():
            with self.subTest(name):
                response = self.post(selection, no_image=True)
                self.assertContains(response, "Seleção de Página inválida")
                self.assertNothingCreated()

    def test_AC_7_no_destination_selected_is_rejected(self):
        """AC-7: nenhum destino → erro de seleção."""
        self.assertContains(self.post([], no_image=True), "Selecione ao menos uma Página")
        self.assertNothingCreated()

    # ---- AC-16 -----------------------------------------------------------
    def test_AC_16_publishing_with_another_users_whatsapp_account_creates_nothing(self):
        """AC-16: publicar com a conta de WhatsApp de outro usuário (mesmo nome de instância) é rejeitado."""
        theirs = make_whatsapp_account(self.bob, "loja")
        response = self.post([theirs], no_image=True)
        self.assertContains(response, "Seleção de Página inválida")
        self.assertNothingCreated()
