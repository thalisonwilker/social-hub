from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import Publication, PublicationTarget

from .image_helpers import make_upload
from .publication_helpers import PublicationTestMixin
from .test_threads_publisher import threads_mocks
from .threads_helpers import THREADS_SETTINGS, make_threads_account

NEW = "social:post_new"
NO_PUBLIC = {**THREADS_SETTINGS, "PUBLIC_BASE_URL": "", "THREADS_REDIRECT_URI": "http://localhost:8000/contas/threads/callback/"}


@override_settings(**THREADS_SETTINGS)
class ThreadsImageFormTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.page = self.make_accounts(1)[0]
        self.profile = make_threads_account(self.alice, "900", username="maria")

    def post(self, destinations, upload=None, no_image=False, text="Olá"):
        data = {"text": text, "accounts": [str(d.pk) for d in destinations]}
        if not no_image:
            data["image"] = upload or make_upload()
        with threads_mocks() as api:
            response = self.client.post(reverse(NEW), data, follow=True)
        self.api = api
        return response

    def assertNothingCreated(self):
        self.assertEqual(Publication.objects.count(), 0)
        self.assertEqual(PublicationTarget.objects.count(), 0)
        self.assertEqual([p for p in Path(self.media).rglob("*") if p.is_file()], [])

    def test_AC_1_threads_only_with_valid_image_stores_it_without_ignored_notice(self):
        """AC-1: só Threads com imagem válida → imagem sanitizada e gravada, sem aviso de imagem ignorada."""
        response = self.post([self.profile])
        pub = Publication.objects.get()
        self.assertTrue(pub.has_image)
        self.assertEqual(pub.image_content_type, "image/jpeg")
        self.assertNotContains(response, "ignorada")
        self.assertNotContains(response, "apenas o texto")

    def test_AC_1_without_image_threads_only_still_creates_text_publication(self):
        """AC-1: só Threads sem imagem continua válido (imagem obrigatória só com Página do Facebook)."""
        self.post([self.profile], no_image=True)
        self.assertFalse(Publication.objects.get().has_image)

    def test_AC_1_facebook_plus_threads_with_image_stores_it(self):
        """AC-1: Facebook + Threads com imagem válida → uma imagem gravada para os dois."""
        self.post([self.page, self.profile])
        self.assertTrue(Publication.objects.get().has_image)

    def test_AC_1_facebook_still_requires_image(self):
        """AC-1: com Página do Facebook, imagem ausente é erro."""
        response = self.post([self.page, self.profile], no_image=True)
        self.assertContains(response, "Escolha uma imagem")
        self.assertNothingCreated()

    def test_AC_2_invalid_image_with_threads_only_is_rejected(self):
        """AC-2: só Threads com imagem inválida → erro da imagem; nada criado."""
        fake = SimpleUploadedFile("falsa.jpg", b"nao sou imagem", content_type="image/jpeg")
        response = self.post([self.profile], upload=fake)
        self.assertContains(response, "não é uma imagem válida")
        self.assertNothingCreated()

    def test_AC_3_ratio_above_ten_is_rejected_in_both_directions(self):
        """AC-3: proporção > 10:1 (larga ou alta) com Threads → erro; nada criado."""
        for size in ((1010, 100), (100, 1010)):
            with self.subTest(size=size):
                response = self.post([self.profile], upload=make_upload(size=size))
                self.assertContains(response, "10 vezes")
                self.assertNothingCreated()

    def test_AC_3_exactly_ten_to_one_is_accepted(self):
        """AC-3: exatamente 10:1 é aceito; pequenas (< 320) também não bloqueiam."""
        self.post([self.profile], upload=make_upload(size=(1000, 100)))
        self.assertEqual(Publication.objects.count(), 1)
        self.post([self.profile], upload=make_upload(size=(100, 100)))
        self.assertEqual(Publication.objects.count(), 2)

    def test_AC_3_extreme_ratio_does_not_block_facebook_only(self):
        """AC-3: a regra de proporção é do Threads; só Facebook não é afetado."""
        self.post([self.page], upload=make_upload(size=(1010, 100)))
        self.assertEqual(Publication.objects.count(), 1)

    @override_settings(**NO_PUBLIC)
    def test_AC_4_threads_with_image_needs_public_address(self):
        """AC-4: Threads + imagem sem endereço público HTTPS → erro claro; nada criado."""
        response = self.post([self.profile])
        self.assertContains(response, "PUBLIC_BASE_URL")
        self.assertNothingCreated()

    @override_settings(**NO_PUBLIC)
    def test_AC_4_public_address_is_not_required_without_image_or_for_facebook_only(self):
        """AC-4: Threads sem imagem, e só Facebook, não exigem endereço público."""
        self.post([self.profile], no_image=True)
        self.post([self.page])
        self.assertEqual(Publication.objects.count(), 2)
