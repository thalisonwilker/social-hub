from cryptography.fernet import Fernet
from django.test import SimpleTestCase, override_settings

from apps.social.conf import REQUIRED_SETTINGS, meta_configured

VALID = {
    "META_APP_ID": "123",
    "META_APP_SECRET": "secret",
    "META_LOGIN_CONFIG_ID": "456",
    "META_REDIRECT_URI": "http://localhost:8080/contas/facebook/callback/",
    "META_TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
}


class ConfigTests(SimpleTestCase):
    @override_settings(**VALID)
    def test_AC_1_configured_when_everything_is_set(self):
        self.assertTrue(meta_configured())

    def test_AC_1_not_configured_when_any_setting_is_empty(self):
        for name in REQUIRED_SETTINGS:
            with self.subTest(missing=name):
                with override_settings(**{**VALID, name: ""}):
                    self.assertFalse(meta_configured())

    @override_settings(**{**VALID, "META_TOKEN_ENCRYPTION_KEY": "nao-e-uma-chave-fernet"})
    def test_AC_1_invalid_encryption_key_counts_as_not_configured(self):
        self.assertFalse(meta_configured())

    @override_settings(**{**VALID, "META_TOKEN_ENCRYPTION_KEY": f"{Fernet.generate_key().decode()},{Fernet.generate_key().decode()}"})
    def test_AC_1_multiple_valid_keys_are_accepted(self):
        self.assertTrue(meta_configured())
