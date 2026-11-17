from unittest import mock

from django.core import signing
from django.test import SimpleTestCase, TestCase, override_settings

from apps.social import public
from apps.social.conf import public_base_url, public_url_configured
from apps.social.models import Publication

from .threads_helpers import HOST, THREADS_SETTINGS

BASE = {**THREADS_SETTINGS, "PUBLIC_BASE_URL": "", "THREADS_IMAGE_URL_TTL_SECONDS": 1800}


class PublicBaseUrlTests(SimpleTestCase):
    @override_settings(**{**BASE, "PUBLIC_BASE_URL": "https://hub.exemplo.com/"})
    def test_AC_5_uses_public_base_url_without_trailing_slash(self):
        """AC-5: a base é o PUBLIC_BASE_URL (origem HTTPS)."""
        self.assertEqual(public_base_url(), "https://hub.exemplo.com")
        self.assertTrue(public_url_configured())

    @override_settings(**BASE)
    def test_AC_5_falls_back_to_redirect_origin(self):
        """AC-5: sem PUBLIC_BASE_URL, usa a origem do THREADS_REDIRECT_URI."""
        self.assertEqual(public_base_url(), f"https://{HOST}")

    @override_settings(**{**BASE, "PUBLIC_BASE_URL": "http://hub.exemplo.com"})
    def test_AC_4_http_public_base_is_ignored(self):
        """AC-4: só HTTPS vale; http cai para a origem do redirect."""
        self.assertEqual(public_base_url(), f"https://{HOST}")

    @override_settings(**{**BASE, "PUBLIC_BASE_URL": "", "THREADS_REDIRECT_URI": "http://localhost:8000/cb/"})
    def test_AC_4_not_configured_without_https(self):
        """AC-4: sem endereço HTTPS, o endereço público não está configurado."""
        self.assertEqual(public_base_url(), "")
        self.assertFalse(public_url_configured())


@override_settings(**BASE)
class PublicTokenTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user("u", password="x")
        self.pub = Publication.objects.create(owner=user, text="t", image="publications/a.png", image_content_type="image/png")

    def test_AC_5_url_has_route_extension_and_signed_token(self):
        """AC-5: URL = base + /publico/imagem.<ext>?t=<token>, com extensão do tipo guardado."""
        url = public.build_public_image_url(self.pub)
        self.assertTrue(url.startswith(f"https://{HOST}/publico/imagem.png?t="))
        token = url.split("?t=", 1)[1]
        self.assertEqual(public.read_image_token(token), (self.pub.pk, ""))
        self.pub.image_content_type = "image/jpeg"
        self.assertIn("/publico/imagem.jpg?t=", public.build_public_image_url(self.pub))

    def test_AC_5_token_expires_after_ttl(self):
        """AC-5: o token vale THREADS_IMAGE_URL_TTL_SECONDS e depois expira."""
        token = public.sign_image_token(self.pub.pk)
        now = signing.time.time()
        with mock.patch("django.core.signing.time.time", return_value=now + 1799):
            self.assertEqual(public.read_image_token(token), (self.pub.pk, ""))
        with mock.patch("django.core.signing.time.time", return_value=now + 1801):
            self.assertEqual(public.read_image_token(token), (None, "expired"))

    def test_AC_5_rejects_tampered_and_foreign_tokens(self):
        """AC-5: vazio, adulterado ou assinado com outra chave é inválido."""
        token = public.sign_image_token(self.pub.pk)
        self.assertEqual(public.read_image_token(""), (None, "invalid"))
        self.assertEqual(public.read_image_token(token[:-2] + "xx"), (None, "invalid"))
        self.assertEqual(public.read_image_token(token.replace(f"{self.pub.pk}.", "999.", 1)), (None, "invalid"))
        with override_settings(SECRET_KEY="outra-chave"):
            self.assertEqual(public.read_image_token(token), (None, "invalid"))

    def test_AC_20_url_never_uses_the_host_header(self):
        """AC-20: a URL vem só do endereço configurado; o Host da requisição não entra."""
        with override_settings(ALLOWED_HOSTS=["*"]):
            self.client.get("/", HTTP_HOST="atacante.example")
            self.assertTrue(public.build_public_image_url(self.pub).startswith(f"https://{HOST}/"))
            self.assertNotIn("atacante", public.build_public_image_url(self.pub))

    @override_settings(**{**BASE, "THREADS_REDIRECT_URI": "http://localhost/cb/"})
    def test_AC_4_build_fails_without_public_address(self):
        """AC-4: sem endereço público não se gera URL."""
        with self.assertRaises(public.PublicUrlNotConfigured):
            public.build_public_image_url(self.pub)
