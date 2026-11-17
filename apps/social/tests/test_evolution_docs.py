import unittest

from django.conf import settings
from django.test import SimpleTestCase

ROOT = settings.BASE_DIR
# O .dockerignore exclui o README da imagem: esses testes rodam no ambiente local e são pulados no container.
readme_present = unittest.skipUnless((ROOT / "README.md").exists(), "README.md fora da imagem (.dockerignore)")


def read(*parts):
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


class EvolutionDocsTests(SimpleTestCase):
    def test_AC_17_env_example_documents_the_variables_without_real_values(self):
        """AC-17: `.env.example` traz EVOLUTION_API_URL e EVOLUTION_TIMEOUT_SECONDS, vazios/padrão, com o aviso do Baileys."""
        env = read(".env.example")
        self.assertIn("\nEVOLUTION_API_URL=\n", env)  # vazio: nenhum endereço real versionado
        self.assertIn("\nEVOLUTION_TIMEOUT_SECONDS=60\n", env)
        self.assertIn("Baileys", env)
        self.assertIn("NÃO é oficial", env)
        self.assertIn("chave da instância", env.lower())
        self.assertIn("global", env.lower())
        for forbidden in ("easypanel", "apikey=", "trycloudflare"):
            self.assertNotIn(forbidden, env.split("EVOLUTION_API_URL=")[1])

    @readme_present
    def test_AC_17_readme_has_the_whatsapp_section_with_the_ban_risk_and_the_instance_key(self):
        """AC-17: o README explica o WhatsApp (Status), o risco de banimento do Baileys e o uso da chave DA INSTÂNCIA (nunca a global)."""
        readme = read("README.md")
        self.assertIn("## WhatsApp (Status) via Evolution API", readme)
        section = readme[readme.index("## WhatsApp (Status) via Evolution API"):]
        section = section[: section.index("\n## ", 5)] if "\n## " in section[5:] else section
        for needle in ("EVOLUTION_API_URL", "EVOLUTION_TIMEOUT_SECONDS", "Baileys", "banimento", "chave da instância", "chave global",
                       "todos os contatos", "base64", "QR"):
            self.assertIn(needle, section, needle)
        self.assertIn("`EVOLUTION_*`", readme)  # tabela de variáveis

    def test_AC_17_no_real_endpoints_in_the_docs(self):
        """AC-17: nada de endereço real da Evolution do operador no repositório."""
        for name in (".env.example", "README.md") if (ROOT / "README.md").exists() else (".env.example",):
            self.assertNotIn("easypanel.host", read(name), name)

    def test_AC_17_adr_0010_records_the_decision(self):
        """AC-17: o ADR-0010 existe, aceito, com credenciais por instância, host fixo e o risco do Baileys."""
        adr = read("docs", "architecture", "adr", "0010-whatsapp-status-via-evolution-api-instancia-chave-cifrada-e-host-fixo.md")
        self.assertIn("# ADR-0010", adr)
        self.assertIn("**Status:** aceito", adr)
        for needle in ("Baileys", "host", "chave da instância", "SSRF", "base64", "ADR-0002", "ADR-0007", "ADR-0009"):
            self.assertIn(needle, adr, needle)

    def test_AC_17_spec_points_to_the_adr_and_testing_doc_mentions_the_fake_transport(self):
        """AC-17: a spec cita o ADR-0010 e o TESTING.md descreve a Evolution falsa no transporte."""
        self.assertIn("0010-whatsapp-status-via-evolution-api", read("specs", "0006-whatsapp-status", "spec.md"))
        testing = read("docs", "engineering", "TESTING.md")
        self.assertIn("Evolution", testing)
        self.assertIn("test_evolution_security.py", testing)

    def test_AC_17_glossary_has_the_whatsapp_terms(self):
        """AC-17: os termos da feature estão no glossário."""
        glossary = read("docs", "glossary.md")
        for term in ("Instância (Evolution)", "Chave da instância", "Conta de WhatsApp", "Status do WhatsApp"):
            self.assertIn(term, glossary)
