import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services import publishing

from .image_helpers import make_image_bytes, make_upload
from .publication_helpers import PublicationTestMixin

NEW = "social:post_new"


class PostNewTests(PublicationTestMixin, TestCase):
    def post(self, accounts, text="Olá, mundo", upload=None, **extra):
        data = {"text": text, "accounts": [str(a.pk) if hasattr(a, "pk") else a for a in accounts]}
        if upload is not False:
            data["image"] = upload or make_upload()
        data.update(extra)
        return self.client.post(reverse(NEW), data)

    def assertNothingCreated(self):
        self.assertEqual(Publication.objects.count(), 0)
        self.assertEqual(PublicationTarget.objects.count(), 0)
        self.publish.assert_not_called()

    # ---- AC-1 / AC-2 -----------------------------------------------------
    def test_AC_1_form_lists_active_pages_and_flags_reauth_ones(self):
        active = self.make_accounts(2)
        stale = self.make_accounts(1, status=SocialAccount.Status.NEEDS_REAUTH, start=3)[0]
        response = self.client.get(reverse(NEW))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="text"')
        self.assertContains(response, 'name="image"')
        self.assertContains(response, 'name="accounts"', count=3)
        self.assertContains(response, "Marcar todas")
        self.assertContains(response, "data-confirm=")
        self.assertContains(response, "data-disable-on-submit")
        self.assertContains(response, "Reconexão necessária")
        html = response.content.decode()
        self.assertEqual(html.count(" disabled"), 1)  # só a conta com reauth
        self.assertIn(f'value="{stale.pk}"', html)
        self.assertContains(response, active[0].name)

    def test_AC_2_without_active_pages_the_form_is_not_offered(self):
        self.make_accounts(1, status=SocialAccount.Status.NEEDS_REAUTH)
        response = self.client.get(reverse(NEW))
        self.assertContains(response, "Conecte ao menos uma Página ativa")
        self.assertNotContains(response, 'name="text"')

    @override_settings(META_APP_ID="")
    def test_AC_2_not_configured_blocks_get_and_post(self):
        accounts = self.make_accounts(1)
        self.assertContains(self.client.get(reverse(NEW)), "Integração com a Meta não configurada")
        response = self.post(accounts)
        self.assertRedirects(response, reverse("social:accounts"), fetch_redirect_response=False)
        self.assertNothingCreated()

    def test_AC_2_post_without_active_pages_creates_nothing(self):
        response = self.post(["1"])
        self.assertRedirects(response, reverse("social:accounts"), fetch_redirect_response=False)
        self.assertNothingCreated()

    # ---- AC-3 ------------------------------------------------------------
    def test_AC_3_valid_post_creates_sends_and_redirects_to_detail(self):
        accounts = self.make_accounts(2)
        response = self.post(accounts, text="Promoção de verão ☀️")
        publication = Publication.objects.get()
        self.assertRedirects(response, reverse("social:post_detail", args=[publication.pk]), fetch_redirect_response=False)
        self.assertEqual(publication.text, "Promoção de verão ☀️")
        self.assertEqual(publication.owner, self.alice)
        self.assertEqual(self.publish.call_count, 2)
        self.assertEqual({t.status for t in publication.targets.all()}, {PublicationTarget.Status.PUBLISHED})
        detail = self.client.get(response["Location"])
        self.assertContains(detail, "Ver post", count=2)

    def test_AC_3_success_message_is_shown(self):
        accounts = self.make_accounts(2)
        response = self.client.post(reverse(NEW), {"text": "x", "accounts": [a.pk for a in accounts], "image": make_upload()}, follow=True)
        self.assertContains(response, "Publicado em 2 Páginas")

    def test_AC_3_only_the_selected_pages_become_targets(self):
        accounts = self.make_accounts(3)
        self.post([accounts[0], accounts[2]])
        names = set(PublicationTarget.objects.values_list("page_name", flat=True))
        self.assertEqual(names, {"Página 1", "Página 3"})
        self.assertEqual(self.publish.call_count, 2)

    # ---- AC-4 ------------------------------------------------------------
    def test_AC_4_invalid_text_is_rejected_and_keeps_input(self):
        accounts = self.make_accounts(1)
        for text, message in (("", "Escreva o texto"), ("   \n  ", "Escreva o texto"), ("a" * 5001, "no máximo 5000")):
            with self.subTest(len(text)):
                response = self.post(accounts, text=text)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.assertNothingCreated()
        self.assertContains(self.post(accounts, text="b" * 5001), "b" * 20)  # mantém o digitado

    def test_AC_4_text_at_the_limit_is_accepted(self):
        accounts = self.make_accounts(1)
        self.post(accounts, text="a" * 5000)
        self.assertEqual(Publication.objects.count(), 1)

    # ---- AC-5 ------------------------------------------------------------
    def test_AC_5_invalid_images_are_rejected(self):
        accounts = self.make_accounts(1)
        gif = make_upload("a.gif", "image/gif", fmt="GIF")
        fake = SimpleUploadedFile("falsa.jpg", b"nao sou uma imagem", content_type="image/jpeg")
        cases = [(False, "Escolha uma imagem"), (fake, "não é uma imagem válida"), (gif, "JPEG ou PNG")]
        for upload, message in cases:
            with self.subTest(message):
                response = self.post(accounts, upload=upload)
                self.assertContains(response, message)
                self.assertNothingCreated()

    @override_settings(PUBLICATION_MAX_IMAGE_BYTES=500)
    def test_AC_5_oversized_image_is_rejected(self):
        accounts = self.make_accounts(1)
        response = self.post(accounts, upload=make_upload(size=(300, 300), fmt="PNG"))
        self.assertContains(response, "no máximo")
        self.assertNothingCreated()

    @override_settings(PUBLICATION_MAX_IMAGE_PIXELS=100)
    def test_AC_5_too_many_pixels_is_rejected(self):
        accounts = self.make_accounts(1)
        self.assertContains(self.post(accounts, upload=make_upload(size=(30, 30))), "grande demais")
        self.assertNothingCreated()

    # ---- AC-6 ------------------------------------------------------------
    def test_AC_6_stored_file_is_sanitized_with_a_random_name(self):
        accounts = self.make_accounts(1)
        exif = Image.Exif()
        exif[0x010F] = "CameraMaker"
        upload = SimpleUploadedFile("selfie-da-maria.jpg", make_image_bytes(exif=exif.tobytes()), content_type="image/jpeg")
        self.post(accounts, upload=upload)
        publication = Publication.objects.get()
        self.assertNotIn("maria", publication.image.name)
        stored = publication.image.open("rb").read()
        self.assertNotIn(b"CameraMaker", stored)
        self.assertEqual(Image.open(io.BytesIO(stored)).format, "JPEG")
        self.assertEqual(publication.image_content_type, "image/jpeg")

    # ---- AC-7 ------------------------------------------------------------
    def test_AC_7_page_selection_is_validated(self):
        mine = self.make_accounts(1)
        theirs = self.make_accounts(1, owner=self.bob, start=10)
        stale = self.make_accounts(1, status=SocialAccount.Status.NEEDS_REAUTH, start=20)
        cases = {
            "nenhuma": ([], "Selecione ao menos uma Página"),
            "de outro usuário": ([theirs[0]], "Seleção de Página inválida"),
            "com reauth": ([stale[0]], "Seleção de Página inválida"),
            "inexistente": (["99999"], "Seleção de Página inválida"),
            "mistura válida+inválida": ([mine[0], theirs[0]], "Seleção de Página inválida"),
            "id não numérico": (["abc"], "Seleção de Página inválida"),
        }
        for name, (selection, message) in cases.items():
            with self.subTest(name):
                response = self.post(selection)
                self.assertContains(response, message)
                self.assertNothingCreated()

    # ---- AC-20 / borda ---------------------------------------------------
    def test_AC_20_post_requires_csrf(self):
        accounts = self.make_accounts(1)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.alice)
        response = strict.post(reverse(NEW), {"text": "x", "accounts": [accounts[0].pk], "image": make_upload()})
        self.assertEqual(response.status_code, 403)
        self.assertNothingCreated()

    def test_edge_storage_failure_creates_nothing_and_shows_message(self):
        from unittest import mock

        accounts = self.make_accounts(1)
        with mock.patch.object(publishing, "create_publication", side_effect=OSError("disco cheio")):
            response = self.post(accounts)
        self.assertContains(response, "Não foi possível salvar a publicação", status_code=500)
        self.assertNothingCreated()

    def test_edge_html_in_text_is_escaped_in_detail(self):
        accounts = self.make_accounts(1)
        response = self.post(accounts, text="<script>alert(1)</script>")
        detail = self.client.get(response["Location"])
        self.assertNotContains(detail, "<script>alert(1)</script>")
        self.assertContains(detail, "&lt;script&gt;alert(1)&lt;/script&gt;")
