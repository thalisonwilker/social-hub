"""Documentação, compose e supersessão das specs anteriores (spec 0007: AC-16, AC-19, AC-20)."""
import re
import unittest

from django.conf import settings
from django.test import SimpleTestCase

ROOT = settings.BASE_DIR
# O .dockerignore tira README.md e docker-compose.yml da imagem: esses testes rodam localmente e pulam no container.
compose_present = unittest.skipUnless((ROOT / "docker-compose.yml").exists(), "docker-compose.yml fora da imagem (.dockerignore)")
readme_present = unittest.skipUnless((ROOT / "README.md").exists(), "README.md fora da imagem (.dockerignore)")


def read(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


def compose_service(name):
    """Bloco do serviço `name` do docker-compose.yml (sem depender de uma lib de YAML)."""
    text = read("docker-compose.yml")
    match = re.search(rf"^  {name}:\n(.*?)(?=^  \w[\w-]*:\n|^\w+:|\Z)", text, re.M | re.S)
    assert match, f"serviço {name} não encontrado"
    return match.group(1)


class ComposeWorkerTests(SimpleTestCase):
    @compose_present
    def test_AC_16_worker_service_uses_the_same_image_and_the_run_worker_command(self):
        """AC-16: serviço `worker` com a mesma imagem e o comando `python manage.py run_worker`."""
        block = compose_service("worker")
        web = compose_service("web")
        self.assertIn("image: social-hub:latest", block)
        self.assertIn("image: social-hub:latest", web)
        self.assertIn('command: ["python", "manage.py", "run_worker"]', block)

    @compose_present
    def test_AC_16_worker_does_not_run_migrations_and_waits_for_a_healthy_web(self):
        """AC-16: `RUN_MIGRATIONS=0` e `depends_on` o `web` saudável (as migrações são do `web`)."""
        block = compose_service("worker")
        self.assertRegex(block, r'RUN_MIGRATIONS:\s*"0"')
        self.assertRegex(block, r"depends_on:\s*\n\s+web:\s*\n\s+condition:\s*service_healthy")

    @compose_present
    def test_AC_16_worker_shares_the_volumes_and_the_settings_of_the_web(self):
        """AC-16: mesmos volumes (`sqlite_data`, `media_data`), mesmos settings de produção e o mesmo caminho do banco."""
        block = compose_service("worker")
        for needle in ("sqlite_data:/data", "media_data:/media", "config.settings.prod", "DATABASE_PATH: /data/db.sqlite3", "MEDIA_ROOT: /media"):
            self.assertIn(needle, block, needle)
        self.assertNotIn("ports:", block)  # o worker não expõe porta

    @compose_present
    def test_AC_16_worker_restarts_stops_gracefully_and_has_a_heartbeat_healthcheck(self):
        """AC-16: `restart: unless-stopped`, `stop_grace_period` ≥ 150 s e healthcheck com `worker_health`."""
        block = compose_service("worker")
        self.assertIn("restart: unless-stopped", block)
        grace = re.search(r"stop_grace_period:\s*(\d+)s", block)
        self.assertIsNotNone(grace)
        self.assertGreaterEqual(int(grace.group(1)), 150)
        self.assertRegex(block, r'test:\s*\["CMD",\s*"python",\s*"manage.py",\s*"worker_health"\]')

    @compose_present
    def test_AC_16_the_web_service_is_unchanged_in_its_essentials(self):
        """AC-16: o `web` segue com a mesma porta, volumes e healthcheck."""
        web = compose_service("web")
        for needle in ("WEB_PORT", "sqlite_data:/data", "media_data:/media", "healthz"):
            self.assertIn(needle, web)


class DocsTests(SimpleTestCase):
    def test_AC_19_env_example_documents_the_publish_mode_and_the_worker_settings(self):
        """AC-19: `.env.example` traz PUBLISH_MODE (comentado, o padrão vem do ambiente) e as três settings do worker."""
        env = read(".env.example")
        self.assertIn("# PUBLISH_MODE=worker", env)
        self.assertNotRegex(env, r"(?m)^PUBLISH_MODE=")  # vazio no .env derrubaria o padrão
        for name in ("WORKER_POLL_SECONDS=2", "WORKER_HEARTBEAT_STALE_SECONDS=180", "PUBLISH_SENDING_STALE_SECONDS=900"):
            self.assertIn(f"\n{name}\n", env)

    @readme_present
    def test_AC_19_readme_explains_the_worker_the_modes_and_the_uncertain_state(self):
        """AC-19: o README explica o worker (`run_worker`, `worker_health`, compose), os modos e o que fazer com "Incerto"."""
        readme = read("README.md")
        self.assertIn("## Publicação em segundo plano (worker)", readme)
        start = readme.index("## Publicação em segundo plano (worker)")
        end = readme.find("\n## ", start + 5)
        section = readme[start:end if end != -1 else None]
        for needle in ("run_worker", "worker_health", "docker compose", "PUBLISH_MODE", "inline", "Incerto", "Já foi publicado",
                       "Reenviar", "WORKER_POLL_SECONDS", "WORKER_HEARTBEAT_STALE_SECONDS", "PUBLISH_SENDING_STALE_SECONDS", "SIGTERM"):
            self.assertIn(needle, section, needle)
        self.assertIn("`PUBLISH_MODE`", readme)  # tabela de variáveis

    @readme_present
    def test_AC_19_readme_no_longer_describes_the_old_synchronous_recovery(self):
        """AC-19: o README não diz mais que o reenvio de `sending` preso acontece após 5 min nem manda usar "Continuar envio" em produção."""
        readme = read("README.md")
        self.assertNotIn("(após 5 min) pode duplicar", readme)
        self.assertIn("modo `inline`", readme.split("## Publicações (texto + imagem em várias Páginas)")[1].split("\n## ")[0])

    def test_AC_19_adr_0011_records_the_decision(self):
        """AC-19: o ADR-0011 existe, aceito, com worker no banco, `uncertain`, recuperação sem reenvio e a substituição parcial dos ADRs 0004 e 0009."""
        adr = read("docs", "architecture", "adr", "0011-publicacao-em-segundo-plano-worker-no-banco-estado-incerto-e-recuperacao-sem-reenvio.md")
        self.assertIn("# ADR-0011", adr)
        self.assertIn("**Status:** aceito", adr)
        for needle in ("worker", "uncertain", "Incerto", "claim", "SQLite", "ADR-0004", "ADR-0009", "inline", "Celery", "heartbeat", "issue #1"):
            self.assertIn(needle, adr, needle)

    def test_AC_19_testing_doc_describes_how_the_worker_is_tested(self):
        """AC-19: o TESTING.md explica `run_once`, o runner `inline`, o teste de concorrência e o teste Node do polling."""
        testing = read("docs", "engineering", "TESTING.md")
        for needle in ("run_once", "inline", "InlinePublishRunner", "test-poll.mjs", "TransactionTestCase"):
            self.assertIn(needle, testing, needle)

    def test_AC_19_spec_links_the_adr_and_the_glossary_has_the_terms(self):
        """AC-19: a spec cita o ADR-0011 e o glossário tem os termos da feature."""
        self.assertIn("0011-publicacao-em-segundo-plano", read("specs", "0007-publicacao-em-segundo-plano", "spec.md"))
        glossary = read("docs", "glossary.md")
        for term in ("Alvo Incerto", "Fila de envio", "Worker", "Heartbeat do worker", "Modo de publicação", "Resolver (alvo incerto)", "Enfileirar"):
            self.assertIn(term, glossary)


class SupersessionNotesTests(SimpleTestCase):
    def section(self, folder, number):
        text = read("specs", folder, "spec.md")
        match = re.search(rf"^### AC-{number}:.*?(?=^### AC-|^## |\Z)", text, re.M | re.S)
        self.assertIsNotNone(match, f"{folder} AC-{number}")
        return match.group(0)

    def test_AC_20_previous_specs_record_the_supersession_by_this_feature(self):
        """AC-20: as specs 0003 (AC-11, AC-13), 0004 (AC-22), 0005 (AC-15, AC-17, AC-18) e 0006 (AC-12, AC-13) apontam para a 0007."""
        cases = {
            "0003-publicar-no-facebook": (11, 13),
            "0004-threads-conectar-e-publicar": (22,),
            "0005-threads-imagem": (15, 17, 18),
            "0006-whatsapp-status": (12, 13),
        }
        for folder, numbers in cases.items():
            for number in numbers:
                with self.subTest(spec=folder, ac=number):
                    section = self.section(folder, number)
                    self.assertIn("0007", section)
                    self.assertIn("inline", section)

    def test_AC_20_the_whatsapp_timeout_message_is_superseded_by_the_uncertain_state(self):
        """AC-20: a 0006 registra que o timeout do WhatsApp agora é o estado Incerto."""
        section = self.section("0006-whatsapp-status", 12)
        self.assertIn("Incerto", section)
        self.assertIn("tempo esgotado", section)
