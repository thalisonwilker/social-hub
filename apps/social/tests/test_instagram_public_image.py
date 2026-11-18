import io
import logging
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from PIL import Image

from apps.social import public
from apps.social.images import sanitize_image
from apps.social.models import PublicationTarget
from apps.social.services import publishing

from .image_helpers import make_image_bytes
from .publication_helpers import PublicationTestMixin
from .test_instagram_model import make_instagram, make_page
from .threads_helpers import HOST, THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status


@override_settings(**THREADS_SETTINGS)
class InstagramPublicImageTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.page = make_page(self.alice, "50")
        self.ig = make_instagram(self.alice, self.page)
        self.anon = Client()

    def publication(self, accounts=None, **image):
        upload = SimpleUploadedFile("x", make_image_bytes(**image)) if image else SimpleUploadedFile("x", make_image_bytes())
        return publishing.create_publication(self.alice, "Legenda", sanitize_image(upload), accounts or [self.ig])

    def url(self, pub, token=None):
        return f"/publico/instagram.jpg?t={token if token is not None else public.sign_image_token(pub.pk)}"

    # ---- AC-11 -------------------------------------------------------------
    def test_AC_11_url_uses_public_base_and_ignores_host_header(self):
        pub = self.publication()
        url = public.build_instagram_image_url(pub)
        self.assertTrue(url.startswith(f"https://{HOST}/publico/instagram.jpg?t="))
        with override_settings(PUBLIC_BASE_URL="https://hub.example.org"):
            self.assertTrue(public.build_instagram_image_url(pub).startswith("https://hub.example.org/publico/instagram.jpg?t="))

    def test_AC_11_url_requires_a_public_address(self):
        pub = self.publication()
        with override_settings(PUBLIC_BASE_URL="", THREADS_REDIRECT_URI=""):
            with self.assertRaises(public.PublicUrlNotConfigured):
                public.build_instagram_image_url(pub)

    def test_AC_11_jpeg_is_served_as_is(self):
        pub = self.publication(fmt="JPEG")
        response = self.anon.get(self.url(pub))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response.content, pub.image.open("rb").read())

    def test_AC_11_png_is_converted_to_jpeg_on_delivery_only(self):
        pub = self.publication(fmt="PNG", mode="RGBA", color=(255, 0, 0, 0))
        stored = pub.image.open("rb").read()
        response = self.anon.get(self.url(pub))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        image = Image.open(io.BytesIO(response.content))
        self.assertEqual(image.format, "JPEG")
        self.assertGreater(min(image.getpixel((1, 1))), 240)  # transparência sobre branco
        self.assertEqual(pub.image.open("rb").read(), stored)  # armazenada intacta
        self.assertEqual(pub.image_content_type, "image/png")

    # ---- AC-12 -------------------------------------------------------------
    def test_AC_12_serves_with_hardened_headers_and_logs(self):
        pub = self.publication()
        with self.assertLogs("apps.social.meta", level="INFO") as logs:
            response = self.anon.get(self.url(pub))
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["X-Robots-Tag"], "noindex")
        self.assertNotIn("Set-Cookie", response)
        self.assertIn("public_image_served", "\n".join(logs.output))

    def test_AC_12_head_has_length_and_no_body(self):
        pub = self.publication()
        response = self.anon.head(self.url(pub))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertEqual(response["Content-Length"], str(len(self.anon.get(self.url(pub)).content)))

    def test_AC_12_works_for_each_in_flight_status(self):
        pub = self.publication()
        for status in (S.PENDING, S.SENDING, S.FAILED):
            pub.targets.update(status=status)
            self.assertEqual(self.anon.get(self.url(pub)).status_code, 200, status)

    def test_AC_12_404_when_instagram_target_is_not_in_flight(self):
        pub = self.publication()
        for status in (S.PUBLISHED, S.UNCERTAIN):
            pub.targets.update(status=status)
            self.assertEqual(self.anon.get(self.url(pub)).status_code, 404, status)

    def test_AC_12_rejects_bad_tokens_uniformly(self):
        pub, other = self.publication(), self.publication()
        bodies = set()
        for token in ("", "lixo", public.sign_image_token(pub.pk)[:-2] + "xx"):
            r = self.anon.get(self.url(pub, token=token))
            self.assertEqual(r.status_code, 404)
            bodies.add(r.content)
        self.assertEqual(len(bodies), 1)
        # token de outra publicação nunca abre esta imagem
        r = self.anon.get(self.url(pub, token=public.sign_image_token(other.pk)))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, other.image.open("rb").read())

    def test_AC_12_expired_token_is_404(self):
        pub = self.publication()
        token = public.sign_image_token(pub.pk)
        with override_settings(THREADS_IMAGE_URL_TTL_SECONDS=-1):
            self.assertEqual(self.anon.get(self.url(pub, token=token)).status_code, 404)

    def test_AC_12_scope_is_per_platform(self):
        threads = make_threads_account(self.alice, "900")
        only_ig = self.publication([self.ig])
        only_threads = self.publication([threads])
        # Threads-only: rota do Instagram recusa; Instagram-only: rota do Threads recusa
        self.assertEqual(self.anon.get(self.url(only_threads)).status_code, 404)
        self.assertEqual(
            self.anon.get(f"/publico/imagem.jpg?t={public.sign_image_token(only_ig.pk)}").status_code, 404
        )
        self.assertEqual(self.anon.get(self.url(only_ig)).status_code, 200)
        self.assertEqual(
            self.anon.get(f"/publico/imagem.jpg?t={public.sign_image_token(only_threads.pk)}").status_code, 200
        )

    def test_AC_12_only_get_and_head(self):
        pub = self.publication()
        for method in ("post", "put", "delete"):
            self.assertEqual(getattr(self.anon, method)(self.url(pub)).status_code, 405, method)

    def test_AC_21_token_and_url_never_in_logs(self):
        pub = self.publication()
        token = public.sign_image_token(pub.pk)
        with self.assertLogs("apps.social.meta", level="INFO") as logs:
            self.anon.get(self.url(pub, token=token))
            self.anon.get(self.url(pub, token="lixo"))
        self.assertNotIn(token, "\n".join(logs.output))
