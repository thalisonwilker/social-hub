import logging
import unittest
from pathlib import Path
from unittest import mock

from django.core import signing
from django.test import Client, TestCase, override_settings

from apps.social import public
from apps.social.models import PublicationTarget

from .publication_helpers import PublicationTestMixin
from .threads_helpers import HOST, THREADS_SETTINGS, make_threads_account

S = PublicationTarget.Status
ROOT = Path(__file__).resolve().parents[3]


@override_settings(**THREADS_SETTINGS)
class PublicImageViewTests(PublicationTestMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.profile = make_threads_account(self.alice, "900")
        self.page = self.make_accounts(1)[0]
        self.pub = self.make_publication([self.profile, self.page])
        self.anon = Client()  # sem login

    def url(self, pub=None, token=None, ext="jpg"):
        pub = pub or self.pub
        return f"/publico/imagem.{ext}?t={token if token is not None else public.sign_image_token(pub.pk)}"

    def get(self, url, **kw):
        return self.anon.get(url, **kw)

    # ---- AC-6 ------------------------------------------------------------
    def test_AC_6_serves_the_sanitized_image_without_login(self):
        """AC-6: token válido + imagem + alvo Threads em andamento → 200 com a imagem, sem login e sem redirecionar."""
        with self.assertLogs("apps.social.meta", level="INFO") as logs:
            response = self.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(b"".join(response.streaming_content), self.pub.image.open("rb").read())
        self.assertIn("public_image_served", "\n".join(logs.output))

    def test_AC_6_head_returns_headers_without_body(self):
        """AC-6: HEAD → 200, tipo e tamanho corretos, sem corpo."""
        response = self.anon.head(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertEqual(response["Content-Length"], str(self.pub.image.size))
        self.assertEqual(response.content, b"")

    def test_AC_6_works_for_each_in_flight_status(self):
        """AC-6: pending, sending e failed contam como 'em andamento'."""
        for status in (S.PENDING, S.SENDING, S.FAILED):
            with self.subTest(status=status):
                self.pub.targets.filter(platform="threads").update(status=status)
                self.assertEqual(self.get(self.url()).status_code, 200)

    # ---- AC-7 ------------------------------------------------------------
    def test_AC_7_invalid_tokens_are_a_uniform_404(self):
        """AC-7: ausente, adulterado, chave errada e extensão incoerente → 404 idêntico."""
        good = public.sign_image_token(self.pub.pk)
        with override_settings(SECRET_KEY="outra"):
            foreign = public.sign_image_token(self.pub.pk)
        bodies = set()
        for label, url in {
            "ausente": "/publico/imagem.jpg",
            "vazio": self.url(token=""),
            "adulterado": self.url(token=good[:-2] + "xx"),
            "outra chave": self.url(token=foreign),
            "extensão errada": self.url(ext="png"),
        }.items():
            with self.subTest(label), self.assertLogs("apps.social.meta", level="INFO") as logs:
                response = self.get(url)
                self.assertEqual(response.status_code, 404)
                bodies.add(response.content)
                self.assertIn("public_image_rejected reason=invalid", "\n".join(logs.output))
        self.assertEqual(len(bodies), 1)

    def test_AC_7_expired_token_is_404(self):
        """AC-7: token expirado → 404 com reason=expired."""
        token = public.sign_image_token(self.pub.pk)
        later = signing.time.time() + 1801
        with mock.patch("django.core.signing.time.time", return_value=later), self.assertLogs("apps.social.meta", level="INFO") as logs:
            self.assertEqual(self.get(self.url(token=token)).status_code, 404)
        self.assertIn("reason=expired", "\n".join(logs.output))

    # ---- AC-8 ------------------------------------------------------------
    def test_AC_8_publication_without_image_is_404(self):
        """AC-8: publicação sem imagem → 404 (reason=no_image)."""
        text_only = self.make_publication([self.profile])
        text_only.image.delete(save=False)
        text_only.image = ""
        text_only.save()
        with self.assertLogs("apps.social.meta", level="INFO") as logs:
            self.assertEqual(self.get(self.url(text_only)).status_code, 404)
        self.assertIn("reason=no_image", "\n".join(logs.output))

    def test_AC_8_published_or_facebook_only_targets_are_404(self):
        """AC-8: sem alvo Threads em andamento (todos publicados / só Facebook) → 404 (reason=not_in_flight)."""
        self.pub.targets.filter(platform="threads").update(status=S.PUBLISHED)
        with self.assertLogs("apps.social.meta", level="INFO") as logs:
            self.assertEqual(self.get(self.url()).status_code, 404)
        self.assertIn("reason=not_in_flight", "\n".join(logs.output))
        fb_only = self.make_publication([self.page])
        self.assertEqual(self.get(self.url(fb_only)).status_code, 404)

    def test_AC_8_missing_file_on_disk_is_404(self):
        """AC-8: arquivo sumiu do volume → 404 genérico, não erro 500."""
        Path(self.pub.image.path).unlink()
        self.assertEqual(self.get(self.url()).status_code, 404)

    # ---- AC-9 ------------------------------------------------------------
    def test_AC_9_security_headers_and_no_session_cookie(self):
        """AC-9: no-store, nosniff, noindex e nenhum Set-Cookie, no 200 e no 404."""
        for url in (self.url(), "/publico/imagem.jpg?t=lixo"):
            with self.subTest(url=url[:30]):
                response = self.get(url)
                self.assertEqual(response["Cache-Control"], "no-store")
                self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                self.assertEqual(response["X-Robots-Tag"], "noindex")
                self.assertEqual(len(response.cookies), 0)

    def test_AC_9_only_get_and_head_are_allowed(self):
        """AC-9: POST/PUT/DELETE → 405 (inclusive sem CSRF)."""
        for method in ("post", "put", "delete", "patch"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.anon, method)(self.url()).status_code, 405)

    def test_AC_9_other_media_routes_still_require_login(self):
        """AC-9: a rota autenticada da imagem continua exigindo login."""
        response = self.anon.get(f"/publicacoes/{self.pub.pk}/imagem/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/entrar/", response["Location"])

    # ---- AC-20 -----------------------------------------------------------
    def test_AC_20_token_only_opens_its_own_publication(self):
        """AC-20: o token de A entrega a imagem de A, nunca a de B."""
        other = self.make_publication([self.profile], text="outra")
        response = self.get(self.url(self.pub))
        self.assertEqual(b"".join(response.streaming_content), self.pub.image.open("rb").read())
        self.assertNotEqual(self.pub.image.name, other.image.name)

    @override_settings(ALLOWED_HOSTS=["*"])
    def test_AC_20_forged_host_does_not_change_the_served_image(self):
        """AC-20: Host forjado não altera o resultado (a rota ignora o Host)."""
        response = self.anon.get(self.url(), HTTP_HOST="atacante.example")
        self.assertEqual(response.status_code, 200)


class GunicornLogTests(TestCase):
    """AC-10: o log de acesso do Gunicorn não registra a query string (onde viaja o token)."""

    def test_AC_10_access_log_format_has_path_without_query(self):
        """AC-10: o formato usa %(U)s (caminho sem query) e não %(r)s/%(q)s."""
        ns = {}
        exec((ROOT / "docker/gunicorn.conf.py").read_text(), ns)
        fmt = ns["access_log_format"]
        self.assertIn("%(U)s", fmt)
        self.assertNotIn("%(r)s", fmt)
        self.assertNotIn("%(q)s", fmt)
        self.assertNotIn("%(f)s", fmt)

    def test_AC_10_formatting_a_real_request_drops_the_token(self):
        """AC-10: formatar uma linha de log com o formato real não deixa o token passar."""
        from gunicorn.config import Config
        from gunicorn.glogging import Logger

        ns = {}
        exec((ROOT / "docker/gunicorn.conf.py").read_text(), ns)
        cfg = Config()
        cfg.set("access_log_format", ns["access_log_format"])
        logger = Logger(cfg)
        req = mock.Mock(headers=[], method="GET", path="/publico/imagem.jpg", query="t=SEGREDO123", version=(1, 1))
        req.uri = "/publico/imagem.jpg?t=SEGREDO123"
        resp = mock.Mock(status="200 OK", response_length=10, headers=[], sent=10)
        environ = {"REMOTE_ADDR": "1.2.3.4", "REQUEST_METHOD": "GET", "PATH_INFO": "/publico/imagem.jpg",
                   "QUERY_STRING": "t=SEGREDO123", "RAW_URI": "/publico/imagem.jpg?t=SEGREDO123", "SERVER_PROTOCOL": "HTTP/1.1"}
        import datetime
        atoms = logger.atoms(resp, req, environ, datetime.timedelta(seconds=0.1))
        line = ns["access_log_format"] % atoms
        self.assertIn("/publico/imagem.jpg", line)
        self.assertNotIn("SEGREDO123", line)

    @unittest.skipUnless((ROOT / "Dockerfile").exists(), "Dockerfile não está na imagem (.dockerignore); checado fora do container")
    def test_AC_10_dockerfile_uses_the_gunicorn_config(self):
        """AC-10: a imagem Docker inicia o Gunicorn com o arquivo de configuração."""
        self.assertIn("docker/gunicorn.conf.py", (ROOT / "Dockerfile").read_text())

    def test_AC_10_app_logs_never_contain_the_token(self):
        """AC-10: os logs do app ao servir/recusar não trazem o token nem a URL."""
        from apps.social import public as pub_mod

        token = pub_mod.sign_image_token(1)
        with self.assertLogs("apps.social.meta", level="INFO") as logs:
            logging.getLogger("apps.social.meta").info("probe")
            Client().get(f"/publico/imagem.jpg?t={token}")
        self.assertNotIn(token, "\n".join(logs.output))
