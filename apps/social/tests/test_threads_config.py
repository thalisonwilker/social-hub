from django.test import SimpleTestCase, override_settings

from apps.social.conf import THREADS_REQUIRED_SETTINGS, threads_configured, threads_redirect_host

from .helpers import KEY

VALID = {
    "THREADS_APP_ID": "1602810271151684",
    "THREADS_APP_SECRET": "segredo-do-threads",
    "THREADS_REDIRECT_URI": "https://abc-def.trycloudflare.com/contas/threads/callback/",
    "META_TOKEN_ENCRYPTION_KEY": KEY,
}


class ThreadsConfigTests(SimpleTestCase):
    @override_settings(**VALID)
    def test_AC_1_configured_when_everything_is_set(self):
        """AC-1: com todas as variáveis e chave válida, o Threads está habilitado."""
        self.assertTrue(threads_configured())

    def test_AC_1_not_configured_when_any_setting_is_empty(self):
        """AC-1: qualquer variável THREADS_* vazia desabilita o Threads."""
        for name in THREADS_REQUIRED_SETTINGS:
            with self.subTest(missing=name), override_settings(**{**VALID, name: ""}):
                self.assertFalse(threads_configured())

    @override_settings(**{**VALID, "META_TOKEN_ENCRYPTION_KEY": ""})
    def test_AC_1_needs_a_valid_encryption_key_to_store_tokens(self):
        """AC-1: sem chave de criptografia não há como guardar tokens."""
        self.assertFalse(threads_configured())

    @override_settings(**{**VALID, "META_TOKEN_ENCRYPTION_KEY": "invalida"})
    def test_AC_1_invalid_encryption_key_counts_as_not_configured(self):
        """AC-1: chave inválida equivale a não configurado."""
        self.assertFalse(threads_configured())

    @override_settings(**VALID)
    def test_redirect_host_is_taken_from_the_redirect_uri(self):
        self.assertEqual(threads_redirect_host(), "abc-def.trycloudflare.com")
        with override_settings(THREADS_REDIRECT_URI="http://localhost:8080/contas/threads/callback/"):
            self.assertEqual(threads_redirect_host(), "localhost:8080")
        with override_settings(THREADS_REDIRECT_URI=""):
            self.assertEqual(threads_redirect_host(), "")

    def test_defaults_match_the_design(self):
        from django.conf import settings

        self.assertEqual(settings.THREADS_GRAPH_VERSION, "v1.0")
        self.assertEqual(settings.THREADS_REFRESH_WINDOW_DAYS, 30)
        self.assertEqual(settings.THREADS_CONTAINER_WAIT_SECONDS, 20)
