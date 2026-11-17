from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import Publication, PublicationTarget, SocialAccount

from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_threads_publisher import PERMALINK, threads_mocks
from .threads_helpers import THREADS_SETTINGS, make_threads_account

NEW = "social:post_new"
S = PublicationTarget.Status


@override_settings(**THREADS_SETTINGS)
class MixedFormTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.page = self.make_accounts(1)[0]
        self.profile = make_threads_account(self.alice, "900", username="maria")

    def post(self, destinations, text="Olá, mundo", upload=None, no_image=False, **extra):
        data = {"text": text, "accounts": [str(d.pk) if hasattr(d, "pk") else d for d in destinations]}
        if not no_image:
            data["image"] = upload or make_upload()
        data.update(extra)
        with threads_mocks() as api:
            response = self.client.post(reverse(NEW), data)
        self.api = api
        return response

    def assertNothingCreated(self):
        self.assertEqual(Publication.objects.count(), 0)
        self.assertEqual(PublicationTarget.objects.count(), 0)
        self.publish.assert_not_called()
        for mock_ in self.api.values():
            mock_.assert_not_called()

    # ---- AC-13 -----------------------------------------------------------
    def test_AC_13_destinations_are_grouped_by_platform_with_rules(self):
        """AC-13: Facebook e Threads agrupados, com Marcar todas e a explicação das regras."""
        response = self.client.get(reverse(NEW))
        self.assertContains(response, "Páginas do Facebook")
        self.assertContains(response, "Perfis do Threads")
        self.assertContains(response, 'name="accounts"', count=2)
        self.assertContains(response, "Marcar todas")
        self.assertContains(response, "@maria")
        self.assertContains(response, "Perfil do Threads · só texto")
        self.assertContains(response, "Obrigatória se marcar uma Página do Facebook")
        self.assertContains(response, "No Threads vai só o texto")
        self.assertContains(response, "limite é de 500")

    def test_AC_13_reauth_profiles_are_disabled_with_a_warning(self):
        """AC-13: perfil em Reconexão necessária aparece desabilitado com aviso e link."""
        make_threads_account(self.alice, "901", username="velho", status=SocialAccount.Status.NEEDS_REAUTH)
        response = self.client.get(reverse(NEW))
        html = response.content.decode()
        self.assertEqual(html.count(" disabled"), 1)
        self.assertContains(response, "Reconexão necessária")
        self.assertContains(response, "O perfil “Velho” precisa ser reconectado")

    @override_settings(THREADS_APP_ID="")
    def test_AC_13_threads_not_configured_makes_profiles_unselectable(self):
        """AC-13: sem THREADS_* os perfis ficam desabilitados e o Facebook segue disponível; POST com perfil é rejeitado."""
        response = self.client.get(reverse(NEW))
        self.assertContains(response, "Integração não configurada")
        self.assertContains(response, 'name="text"')  # o formulário continua para o Facebook
        response = self.post([self.profile], no_image=True)
        self.assertContains(response, "Seleção de Página inválida")
        self.assertNothingCreated()

    # ---- AC-14 -----------------------------------------------------------
    def test_AC_14_facebook_requires_an_image(self):
        """AC-14: Página do Facebook marcada e sem imagem → erro; nada criado."""
        response = self.post([self.page], no_image=True)
        self.assertContains(response, "Escolha uma imagem")
        self.assertNothingCreated()

    def test_AC_14_facebook_plus_threads_requires_an_image(self):
        """AC-14: Facebook + Threads sem imagem → erro de imagem; nada criado."""
        response = self.post([self.page, self.profile], no_image=True)
        self.assertContains(response, "Escolha uma imagem")
        self.assertNothingCreated()

    def test_AC_14_invalid_image_is_rejected_when_there_is_a_facebook_page(self):
        """AC-14: imagem inválida continua sendo erro quando há Página do Facebook."""
        fake = SimpleUploadedFile("falsa.jpg", b"nao sou imagem", content_type="image/jpeg")
        response = self.post([self.page, self.profile], upload=fake)
        self.assertContains(response, "não é uma imagem válida")
        self.assertNothingCreated()

    def test_AC_14_threads_only_without_image_is_created_without_image(self):
        """AC-14: só Threads sem imagem → publicação criada sem imagem e enviada."""
        response = self.post([self.profile], no_image=True)
        pub = Publication.objects.get()
        self.assertRedirects(response, reverse("social:post_detail", args=[pub.pk]), fetch_redirect_response=False)
        self.assertFalse(pub.has_image)
        self.assertEqual(pub.targets.get().status, S.PUBLISHED)
        self.publish.assert_not_called()

    def test_AC_14_threads_only_ignores_a_provided_image_even_if_invalid(self):
        """AC-14: só Threads com imagem → ignorada (nem validada, nem gravada, nem enviada), com aviso."""
        fake = SimpleUploadedFile("qualquer.jpg", b"nem e imagem", content_type="image/jpeg")
        with threads_mocks():
            response = self.client.post(reverse(NEW), {"text": "x", "accounts": [self.profile.pk], "image": fake}, follow=True)
        pub = Publication.objects.get()
        self.assertFalse(pub.has_image)
        self.assertContains(response, "a imagem foi ignorada")
        from pathlib import Path
        self.assertEqual([p for p in Path(self.media).rglob("*") if p.is_file()], [])

    def test_AC_14_facebook_plus_threads_with_valid_image_creates_both(self):
        """AC-14: Facebook + Threads com imagem válida → cria os dois alvos e grava a imagem."""
        self.post([self.page, self.profile])
        pub = Publication.objects.get()
        self.assertTrue(pub.has_image)
        self.assertEqual(sorted(pub.targets.values_list("platform", flat=True)), ["facebook_page", "threads"])

    # ---- AC-15 -----------------------------------------------------------
    def test_AC_15_threads_text_over_500_is_rejected(self):
        """AC-15: texto com peso > 500 e Threads marcado → erro do Threads; nada criado."""
        response = self.post([self.profile], text="a" * 501, no_image=True)
        self.assertContains(response, "No Threads o texto pode ter até 500")
        self.assertNothingCreated()
        self.post([self.profile], text="a" * 500, no_image=True)
        self.assertEqual(Publication.objects.count(), 1)

    def test_AC_15_emoji_weigh_more_in_the_threads_limit(self):
        """AC-15: 125 emoji (4 bytes) estão no limite; 126 passam e são rejeitados."""
        self.assertContains(self.post([self.profile], text="👍" * 126, no_image=True), "No Threads o texto pode ter até 500")
        self.assertNothingCreated()
        self.post([self.profile], text="👍" * 125, no_image=True)
        self.assertEqual(Publication.objects.count(), 1)

    def test_AC_15_more_than_five_unique_links_is_rejected(self):
        """AC-15: mais de 5 links diferentes → erro; repetidos contam uma vez."""
        six = " ".join(f"https://site.com/{i}" for i in range(6))
        self.assertContains(self.post([self.profile], text=six, no_image=True), "no máximo 5 links diferentes")
        self.assertNothingCreated()
        five_repeated = " ".join(f"https://site.com/{i % 5}" for i in range(12))
        self.post([self.profile], text=five_repeated, no_image=True)
        self.assertEqual(Publication.objects.count(), 1)

    def test_AC_15_without_threads_the_limit_is_5000(self):
        """AC-15: sem Threads marcado vale o limite de 5000 da 0003."""
        self.post([self.page], text="a" * 600)
        self.assertEqual(Publication.objects.count(), 1)
        self.assertContains(self.post([self.page], text="a" * 5001), "no máximo 5000")

    def test_AC_15_threads_limit_also_applies_to_mixed_destinations(self):
        """AC-15: Facebook + Threads com texto de 501 → erro (vale o limite do Threads)."""
        response = self.post([self.page, self.profile], text="a" * 501)
        self.assertContains(response, "No Threads o texto pode ter até 500")
        self.assertNothingCreated()

    def test_AC_15_empty_text_is_still_invalid(self):
        """AC-15: texto vazio continua inválido, inclusive só Threads."""
        self.assertContains(self.post([self.profile], text="   ", no_image=True), "Escreva o texto")
        self.assertNothingCreated()

    # ---- AC-16 -----------------------------------------------------------
    def test_AC_16_destination_selection_is_validated_for_both_platforms(self):
        """AC-16: nenhum destino, de outro usuário, em reauth, inexistente ou misto inválido → erro; nada criado."""
        theirs = make_threads_account(self.bob, "950", username="bob_t")
        stale = make_threads_account(self.alice, "951", username="velho", status=SocialAccount.Status.NEEDS_REAUTH)
        cases = {
            "nenhum": ([], "Selecione ao menos uma Página"),
            "perfil de outro usuário": ([theirs], "Seleção de Página inválida"),
            "perfil em reauth": ([stale], "Seleção de Página inválida"),
            "inexistente": (["99999"], "Seleção de Página inválida"),
            "válido + de outro": ([self.profile, theirs], "Seleção de Página inválida"),
        }
        for name, (selection, message) in cases.items():
            with self.subTest(name):
                response = self.post(selection, no_image=True)
                self.assertContains(response, message)
                self.assertNothingCreated()

    # ---- AC-21 -----------------------------------------------------------
    def test_AC_21_mixed_post_publishes_each_platform_and_shows_both_results(self):
        """AC-21: Facebook (foto + texto) e Threads (só texto) publicados; detalhe com os dois links."""
        with threads_mocks() as api:
            response = self.client.post(
                reverse(NEW), {"text": "Promo ☀️", "accounts": [self.page.pk, self.profile.pk], "image": make_upload()}, follow=True)
        self.assertContains(response, "Publicado em 2 Páginas")
        self.assertEqual(self.publish.call_count, 1)
        api["create_text_container"].assert_called_once_with("900", "threads-long-token", "Promo ☀️")
        self.assertContains(response, f"https://www.facebook.com/{self.page.external_id}_77")
        self.assertContains(response, PERMALINK)
        self.assertContains(response, "Perfil do Threads")
        self.assertContains(response, "Página do Facebook")

    # ---- AC-23 -----------------------------------------------------------
    def test_AC_23_threads_only_publication_has_no_image_anywhere(self):
        """AC-23: detalhe e histórico mostram um ícone no lugar da imagem; a rota da imagem responde 404."""
        self.post([self.profile], no_image=True)
        pub = Publication.objects.get()
        detail = self.client.get(reverse("social:post_detail", args=[pub.pk]))
        self.assertContains(detail, "Publicação só de texto")
        self.assertNotContains(detail, reverse("social:post_image", args=[pub.pk]))
        listing = self.client.get(reverse("social:posts"))
        self.assertNotContains(listing, reverse("social:post_image", args=[pub.pk]))
        self.assertEqual(self.client.get(reverse("social:post_image", args=[pub.pk])).status_code, 404)

    def test_AC_23_facebook_publications_keep_showing_the_image(self):
        """AC-23: publicações do Facebook continuam exibindo a imagem."""
        self.post([self.page])
        pub = Publication.objects.get()
        self.assertContains(self.client.get(reverse("social:post_detail", args=[pub.pk])), reverse("social:post_image", args=[pub.pk]))
        self.assertEqual(self.client.get(reverse("social:post_image", args=[pub.pk])).status_code, 200)

    def test_AC_23_published_threads_target_without_link_says_so(self):
        """AC-23: alvo publicado sem permalink mostra 'link indisponível'."""
        self.post([self.profile], no_image=True)
        PublicationTarget.objects.update(permalink="")
        pub = Publication.objects.get()
        self.assertContains(self.client.get(reverse("social:post_detail", args=[pub.pk])), "link indisponível")


class Spec0003UpdatedTests(TestCase):
    def test_AC_27_spec_0003_records_the_changes_made_by_this_feature(self):
        """AC-27: a spec 0003 registra o AC-1 (destinos mistos) e o AC-5 (imagem só com Página do Facebook)."""
        from django.conf import settings

        spec = (settings.BASE_DIR / "specs" / "0003-publicar-no-facebook" / "spec.md").read_text(encoding="utf-8")
        ac1 = spec[spec.index("### AC-1:"):spec.index("### AC-2:")]
        ac5 = spec[spec.index("### AC-5:"):spec.index("### AC-6:")]
        self.assertIn("perfis do Threads", ac1)
        self.assertIn("0004", ac1)
        self.assertIn("apenas quando há Página do Facebook", ac5)
        self.assertIn("0004", ac5)
