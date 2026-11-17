from cryptography.fernet import Fernet
from django.test import SimpleTestCase, override_settings

from apps.social.crypto import TokenCryptoError, decrypt_token, encrypt_token

KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()


class CryptoTests(SimpleTestCase):
    @override_settings(META_TOKEN_ENCRYPTION_KEY=KEY_A)
    def test_AC_16_roundtrip_and_ciphertext_is_not_plaintext(self):
        token = "EAAB-token-secreto-123"
        encrypted = encrypt_token(token)
        self.assertNotIn(token, encrypted)
        self.assertEqual(decrypt_token(encrypted), token)

    def test_AC_16_key_rotation_old_tokens_still_decrypt(self):
        with override_settings(META_TOKEN_ENCRYPTION_KEY=KEY_A):
            old = encrypt_token("abc")
        with override_settings(META_TOKEN_ENCRYPTION_KEY=f"{KEY_B},{KEY_A}"):
            self.assertEqual(decrypt_token(old), "abc")
            new = encrypt_token("abc")  # criptografa com a primeira chave
        with override_settings(META_TOKEN_ENCRYPTION_KEY=KEY_B):
            self.assertEqual(decrypt_token(new), "abc")

    @override_settings(META_TOKEN_ENCRYPTION_KEY="")
    def test_AC_16_missing_key_raises_controlled_error(self):
        with self.assertRaises(TokenCryptoError):
            encrypt_token("abc")

    @override_settings(META_TOKEN_ENCRYPTION_KEY="chave-invalida")
    def test_AC_16_invalid_key_raises_controlled_error(self):
        with self.assertRaises(TokenCryptoError):
            encrypt_token("abc")

    def test_AC_16_wrong_key_raises_without_leaking_secret(self):
        with override_settings(META_TOKEN_ENCRYPTION_KEY=KEY_A):
            encrypted = encrypt_token("segredo-xyz")
        with override_settings(META_TOKEN_ENCRYPTION_KEY=KEY_B):
            with self.assertRaises(TokenCryptoError) as ctx:
                decrypt_token(encrypted)
        self.assertNotIn("segredo-xyz", str(ctx.exception))
        self.assertNotIn(KEY_B, str(ctx.exception))
