from django.test import SimpleTestCase, override_settings

from apps.social import conf
from apps.social.models import PublicationTarget, SocialAccount
from apps.social.validators import clean_instance_key, is_valid_instance_name

from .helpers import KEY

VALID = {"EVOLUTION_API_URL": "https://evo.exemplo.host", "META_TOKEN_ENCRYPTION_KEY": KEY}


class EvolutionConfigTests(SimpleTestCase):
    @override_settings(**VALID)
    def test_AC_4_configured_with_https_url_and_valid_encryption_key(self):
        """AC-4: URL HTTPS e chave de criptografia válida habilitam a integração."""
        self.assertTrue(conf.evolution_configured())
        self.assertEqual(conf.evolution_base_url(), "https://evo.exemplo.host")

    def test_AC_4_not_configured_when_url_is_empty_or_not_https(self):
        """AC-4: URL vazia, HTTP ou inválida desabilita a integração."""
        for url in ("", "http://evo.exemplo.host", "ftp://evo.exemplo.host", "evo.exemplo.host", "https://"):
            with self.subTest(url=url), override_settings(**{**VALID, "EVOLUTION_API_URL": url}):
                self.assertFalse(conf.evolution_configured())
                self.assertEqual(conf.evolution_base_url(), "")

    @override_settings(**{**VALID, "META_TOKEN_ENCRYPTION_KEY": ""})
    def test_AC_4_needs_an_encryption_key_to_store_instance_keys(self):
        """AC-4: sem chave de criptografia não há como guardar a chave da instância."""
        self.assertFalse(conf.evolution_configured())

    @override_settings(**{**VALID, "EVOLUTION_API_URL": "https://evo.exemplo.host/manager/?x=1#y"})
    def test_AC_14_base_url_keeps_only_the_origin(self):
        """AC-14: do que for configurado só a origem HTTPS é usada (caminho, query e fragmento são descartados)."""
        self.assertEqual(conf.evolution_base_url(), "https://evo.exemplo.host")

    @override_settings(**{**VALID, "EVOLUTION_API_URL": "https://usuario:senha@evo.exemplo.host"})
    def test_AC_14_credentials_inside_the_url_are_not_accepted(self):
        """AC-14: URL com usuário/senha embutidos é considerada não configurada."""
        self.assertFalse(conf.evolution_configured())

    def test_AC_12_timeout_comes_from_settings_with_a_default(self):
        """AC-12: o timeout das chamadas vem de EVOLUTION_TIMEOUT_SECONDS (padrão 60)."""
        from django.conf import settings

        self.assertEqual(settings.EVOLUTION_TIMEOUT_SECONDS, 60)


class InstanceNameTests(SimpleTestCase):
    def test_AC_14_valid_instance_names(self):
        """AC-14: letras, números, hífen e sublinhado, de 1 a 64 caracteres."""
        for name in ("a", "minha-instancia", "Loja_01", "x" * 64):
            with self.subTest(name=name):
                self.assertTrue(is_valid_instance_name(name))

    def test_AC_14_hostile_instance_names_are_rejected(self):
        """AC-14: vazio, > 64, `/`, `..`, `?`, `#`, `%`, espaço, quebra de linha e não ASCII são rejeitados."""
        for name in ("", "x" * 65, "a/b", "..", "a..b", "a?b", "a#b", "a%2Fb", "a b", "a\nb", "ação", "a.b", "a:b", "a\\b", None):
            with self.subTest(name=name):
                self.assertFalse(is_valid_instance_name(name))

    def test_AC_2_instance_key_is_trimmed_and_cleaned_of_inner_whitespace(self):
        """AC-2: espaços e quebras de linha de colagem são removidos; chave vazia vira string vazia."""
        self.assertEqual(clean_instance_key("  ABC-123\n"), "ABC-123")
        self.assertEqual(clean_instance_key("AB C\t12\r\n3"), "ABC123")
        self.assertEqual(clean_instance_key("   "), "")
        self.assertEqual(clean_instance_key(None), "")


class PlatformTests(SimpleTestCase):
    def test_AC_4_whatsapp_status_is_a_platform_of_accounts_and_targets(self):
        """AC-4: a plataforma existe nas escolhas de conta e de alvo."""
        self.assertEqual(SocialAccount.Platform.WHATSAPP_STATUS.value, "whatsapp_status")
        self.assertEqual(SocialAccount.Platform.WHATSAPP_STATUS.label, "WhatsApp (Status)")
        values = [c[0] for c in PublicationTarget._meta.get_field("platform").choices]
        self.assertIn("whatsapp_status", values)
