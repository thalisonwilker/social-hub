from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.social.models import SocialAccount
from apps.social.services.meta import MetaApiError

from .threads_helpers import CODE, HOST, LONG, SHORT, THREADS_SETTINGS, make_threads_account, threads_api

CONNECT = "social:threads_connect"
CALLBACK = "social:threads_callback"


@override_settings(**THREADS_SETTINGS)
class ThreadsConnectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice", password="x")
        cls.bob = User.objects.create_user("bob", password="x")

    def setUp(self):
        self.client.force_login(self.alice)

    def start(self):
        response = self.client.post(reverse(CONNECT), HTTP_HOST=HOST)
        return parse_qs(urlparse(response["Location"]).query)["state"][0]

    def callback(self, **params):
        return self.client.get(reverse(CALLBACK), params, HTTP_HOST=HOST, follow=True)

    # ---- AC-1 ------------------------------------------------------------
    @override_settings(THREADS_APP_SECRET="")
    def test_AC_1_not_configured_disables_the_button_and_blocks_the_flow(self):
        """AC-1: sem THREADS_* o botão fica desabilitado e o POST não inicia o OAuth."""
        page = self.client.get(reverse("social:accounts"))
        self.assertContains(page, "Integração com o Threads não configurada")
        html = page.content.decode()
        threads_form = html[html.index(reverse(CONNECT)):]
        button = threads_form[threads_form.index("<button"):threads_form.index("</button>")]
        self.assertIn("Conectar conta", button)  # spec 0017: a tela virou a central de conexões
        self.assertIn("disabled", button)
        response = self.client.post(reverse(CONNECT), HTTP_HOST=HOST, follow=True)
        self.assertRedirects(response, reverse("social:accounts"))
        self.assertContains(response, "Integração com o Threads não configurada")
        self.assertNotIn("threads_oauth_state", self.client.session)

    def test_AC_1_facebook_keeps_working_without_threads(self):
        """AC-1: o resto do sistema (Facebook) não depende do Threads."""
        with override_settings(THREADS_APP_ID=""):
            self.assertEqual(self.client.get(reverse("social:accounts")).status_code, 200)
            self.assertEqual(self.client.get(reverse("social:posts")).status_code, 200)

    # ---- AC-2 / AC-3 -----------------------------------------------------
    def test_AC_2_connect_redirects_to_threads_with_state(self):
        """AC-2: POST pelo host do redirect gera state e redireciona para threads.com/oauth/authorize."""
        response = self.client.post(reverse(CONNECT), HTTP_HOST=HOST)
        self.assertEqual(response.status_code, 302)
        url = urlparse(response["Location"])
        self.assertEqual(f"{url.scheme}://{url.netloc}{url.path}", "https://threads.com/oauth/authorize")
        q = parse_qs(url.query)
        self.assertEqual(q["client_id"], ["1602810271151684"])
        self.assertEqual(q["scope"], ["threads_basic,threads_content_publish,threads_delete"])
        self.assertEqual(q["response_type"], ["code"])
        self.assertEqual(q["redirect_uri"], [THREADS_SETTINGS["THREADS_REDIRECT_URI"]])
        self.assertEqual(q["state"][0], self.client.session["threads_oauth_state"]["value"])

    def test_AC_2_connect_rejects_get(self):
        """AC-2: GET na rota de conectar é recusado (405)."""
        self.assertEqual(self.client.get(reverse(CONNECT), HTTP_HOST=HOST).status_code, 405)

    def test_AC_3_wrong_host_warns_and_does_not_start_oauth(self):
        """AC-3: iniciar por localhost (host diferente do redirect) avisa o host correto e não inicia o OAuth."""
        response = self.client.post(reverse(CONNECT), HTTP_HOST="localhost", follow=True)
        self.assertRedirects(response, reverse("social:accounts"))
        self.assertContains(response, f"Acesse o Social Hub por {HOST} para conectar o Threads")
        self.assertNotIn("threads_oauth_state", self.client.session)

    # ---- AC-4 / AC-5 -----------------------------------------------------
    def test_AC_4_valid_callback_connects_the_profile(self):
        """AC-4: troca code → token longo → perfil; cria conta threads com token cifrado e validade; sem tela de seleção."""
        state = self.start()
        with threads_api() as api:
            response = self.callback(code=CODE, state=state)
        self.assertRedirects(response, reverse("social:accounts"))
        self.assertContains(response, "Perfil @maria conectado")
        api["exchange_code"].assert_called_once_with(CODE)
        api["extend_token"].assert_called_once_with(SHORT)
        api["get_profile"].assert_called_once_with("900", LONG)
        account = SocialAccount.objects.get()
        self.assertEqual((account.owner, account.platform, account.external_id, account.username, account.status),
                         (self.alice, "threads", "900", "maria", "active"))
        self.assertEqual(account.get_token(), LONG)
        self.assertNotIn(LONG, account.access_token_enc)
        self.assertNotIn(SHORT, account.access_token_enc)
        expected = timezone.now() + timedelta(seconds=5183944)
        self.assertLess(abs((account.token_expires_at - expected).total_seconds()), 5)
        self.assertLess(abs((account.token_refreshed_at - timezone.now()).total_seconds()), 5)

    def test_AC_5_reconnecting_updates_the_same_account(self):
        """AC-5: reconectar o mesmo perfil atualiza token, validade e status, sem duplicar; perfil diferente cria outra conta."""
        old = make_threads_account(self.alice, "900", status=SocialAccount.Status.NEEDS_REAUTH, token="velho")
        old.last_error = "Meta erro 190"
        old.save()
        state = self.start()
        with threads_api():
            self.callback(code=CODE, state=state)
        self.assertEqual(SocialAccount.objects.count(), 1)
        old.refresh_from_db()
        self.assertEqual((old.status, old.last_error, old.get_token()), ("active", "", LONG))
        state = self.start()
        with threads_api(exchange={"access_token": SHORT, "user_id": "901"}, profile={**{"id": "901", "username": "joao", "name": "João", "picture_url": ""}}):
            self.callback(code=CODE, state=state)
        self.assertEqual(SocialAccount.objects.count(), 2)

    # ---- AC-6 / AC-7 / AC-8 ----------------------------------------------
    def test_AC_6_user_cancels(self):
        """AC-6: error=access_denied → sem chamadas, nada criado, mensagem de cancelamento."""
        self.start()
        with threads_api() as api:
            response = self.callback(error="access_denied", error_reason="user_denied")
        self.assertContains(response, "Autorização cancelada")
        for mock_ in api.values():
            mock_.assert_not_called()
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_AC_7_invalid_state_is_rejected(self):
        """AC-7: state ausente, errado ou reutilizado é rejeitado, sem chamar a API, e logado."""
        self.start()
        for params in ({"code": CODE, "state": "errado"}, {"code": CODE}):
            with self.subTest(params), threads_api() as api, self.assertLogs("apps.social.meta", "WARNING") as logs:
                response = self.callback(**params)
                self.start()
            self.assertContains(response, "Não foi possível validar a conexão")
            self.assertIn("threads_state_rejected", "\n".join(logs.output))
            for mock_ in api.values():
                mock_.assert_not_called()
        state = self.start()
        with threads_api():
            self.callback(code=CODE, state=state)
        with threads_api() as api:
            reused = self.callback(code=CODE, state=state)
        self.assertContains(reused, "Não foi possível validar a conexão")
        api["exchange_code"].assert_not_called()

    def test_AC_8_meta_failures_create_and_change_nothing(self):
        """AC-8: falha na troca, no token longo ou no perfil (ou code ausente) mostra mensagem genérica e não altera nada."""
        existing = make_threads_account(self.alice, "900", token="intacto")
        before = existing.access_token_enc
        failures = {
            "troca do code": {"exchange_error": MetaApiError("x", code=400)},
            "token longo": {"extend_error": MetaApiError("x", code="network")},
            "perfil": {"profile_error": MetaApiError("x", code=190)},
        }
        for name, kwargs in failures.items():
            with self.subTest(name):
                state = self.start()
                with threads_api(**kwargs):
                    response = self.callback(code=CODE, state=state)
                self.assertContains(response, "Não foi possível concluir a conexão com o Threads")
        state = self.start()
        response = self.callback(state=state)  # sem code
        self.assertContains(response, "Não foi possível concluir a conexão com o Threads")
        existing.refresh_from_db()
        self.assertEqual(existing.access_token_enc, before)
        self.assertEqual(SocialAccount.objects.count(), 1)

    # ---- AC-26 -----------------------------------------------------------
    def test_AC_26_anonymous_users_are_sent_to_login(self):
        """AC-26: conectar e callback exigem login."""
        self.client.logout()
        for name, method in ((CONNECT, "post"), (CALLBACK, "get")):
            with self.subTest(name), threads_api() as api:
                response = getattr(self.client, method)(reverse(name), HTTP_HOST=HOST)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("accounts:login")))
                for mock_ in api.values():
                    mock_.assert_not_called()
