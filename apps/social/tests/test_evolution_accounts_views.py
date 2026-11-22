import logging
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services.evolution import EvolutionClient

from .evolution_helpers import EVOLUTION_SETTINGS, INSTANCE_KEY, evolution_state, make_whatsapp_account

NEW = "social:whatsapp_new"
WA = SocialAccount.Platform.WHATSAPP_STATUS


@override_settings(**EVOLUTION_SETTINGS)
class WhatsAppAccountsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice", password="x")
        cls.bob = User.objects.create_user("bob", password="x")

    def setUp(self):
        self.client.force_login(self.alice)

    def register(self, instance="loja", key=INSTANCE_KEY, label="", follow=True):
        return self.client.post(reverse(NEW), {"instance_name": instance, "api_key": key, "label": label}, follow=follow)

    # ---- AC-1 ------------------------------------------------------------
    def test_AC_1_registers_an_open_instance_with_the_key_encrypted(self):
        """AC-1: instância `open` → conta ativa do usuário, chave cifrada, mensagem de sucesso, chave não exibida."""
        with evolution_state("open") as state:
            response = self.register(instance="minha-loja", label="Loja do centro")
        account = SocialAccount.objects.get()
        self.assertEqual((account.owner, account.platform, account.external_id), (self.alice, WA, "minha-loja"))
        self.assertEqual(account.name, "Loja do centro")
        self.assertEqual(account.status, SocialAccount.Status.ACTIVE)
        self.assertNotIn(INSTANCE_KEY, account.access_token_enc)
        self.assertEqual(account.get_token(), INSTANCE_KEY)
        self.assertIsNone(account.token_expires_at)
        self.assertRedirects(response, reverse("social:accounts"))
        self.assertContains(response, "foi conectada")
        self.assertNotContains(response, INSTANCE_KEY)
        args, _ = state.call_args
        self.assertEqual(args[:2], ("minha-loja", INSTANCE_KEY))

    def test_AC_1_label_is_optional_and_defaults_to_the_instance_name(self):
        """AC-1: sem rótulo, o nome da conta é o nome da instância."""
        with evolution_state("open"):
            self.register(instance="minha-loja")
        self.assertEqual(SocialAccount.objects.get().name, "minha-loja")

    def test_AC_1_key_pasted_with_spaces_and_newlines_is_cleaned(self):
        """AC-1: espaços/quebras de linha ao colar a chave são removidos antes de validar e gravar."""
        with evolution_state("open") as state:
            self.register(key=f"  {INSTANCE_KEY[:5]}\n{INSTANCE_KEY[5:]}  ")
        self.assertEqual(SocialAccount.objects.get().get_token(), INSTANCE_KEY)
        self.assertEqual(state.call_args.args[1], INSTANCE_KEY)

    # ---- AC-2 (matriz de cadastro) -----------------------------------------
    def assertRejected(self, response, message):
        self.assertEqual(SocialAccount.objects.count(), 0)
        self.assertContains(response, message)
        self.assertNotContains(response, INSTANCE_KEY)
        self.assertNotContains(response, "texto cru")

    def test_AC_2_instance_not_open_is_rejected(self):
        """AC-2: estado diferente de `open` (`close`, `connecting`) → recusa específica; nada gravado."""
        for state_name in ("close", "connecting"):
            with self.subTest(state=state_name), evolution_state(state_name):
                self.assertRejected(self.register(follow=False), "O número não está conectado na Evolution")

    def test_AC_2_evolution_errors_map_to_specific_messages(self):
        """AC-2: chave recusada, instância inexistente e Evolution inacessível têm mensagens próprias."""
        cases = {
            "auth": "Chave recusada pela Evolution",
            "not_found": "Instância não encontrada",
            "timeout": "Não foi possível falar com a Evolution",
            "network": "Não foi possível falar com a Evolution",
            "server": "Não foi possível falar com a Evolution",
            "bad_response": "Não foi possível falar com a Evolution",
            "rate_limit": "Não foi possível falar com a Evolution",
        }
        for code, message in cases.items():
            with self.subTest(code=code), evolution_state(error_code=code):
                self.assertRejected(self.register(follow=False), message)

    def test_AC_2_invalid_names_and_empty_key_never_call_the_evolution(self):
        """AC-2: nome vazio, longo ou com `/ . ? # %`/espaço, e chave vazia → erro de formulário, nenhuma chamada."""
        for name in ("", "x" * 65, "a/b", "..", "a.b", "a?b", "a#b", "a%2Fb", "a b"):
            with self.subTest(name=name), evolution_state("open") as state:
                response = self.register(instance=name, follow=False)
                self.assertEqual(SocialAccount.objects.count(), 0)
                self.assertContains(response, "Nome de instância inválido")
                state.assert_not_called()
        with evolution_state("open") as state:
            response = self.register(key="   ", follow=False)
            self.assertContains(response, "Informe a chave da instância")
            state.assert_not_called()
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_AC_2_the_key_is_never_echoed_back_in_the_form(self):
        """AC-2/AC-14: ao reexibir o formulário com erro, o nome é mantido e a chave nunca é devolvida na página."""
        with evolution_state("close"):
            response = self.register(instance="minha-loja", follow=False)
        html = response.content.decode()
        self.assertIn('value="minha-loja"', html)
        self.assertNotIn(INSTANCE_KEY, html)

    # ---- AC-3 ------------------------------------------------------------
    def test_AC_3_registering_again_updates_the_same_account(self):
        """AC-3: mesmo usuário + mesma instância atualiza a chave, volta a `active`, limpa o erro e não duplica."""
        old = make_whatsapp_account(self.alice, "loja", status=SocialAccount.Status.NEEDS_REAUTH, key="chave-antiga")
        old.last_error = "Evolution: instância desconectada"
        old.save()
        with evolution_state("open"):
            self.register(instance="loja", key="chave-nova-999")
        account = SocialAccount.objects.get()
        self.assertEqual(account.pk, old.pk)
        self.assertEqual(account.get_token(), "chave-nova-999")
        self.assertEqual(account.status, SocialAccount.Status.ACTIVE)
        self.assertEqual(account.last_error, "")

    def test_AC_3_recadastro_keeps_the_label_when_none_is_given(self):
        """AC-3: sem novo rótulo, o nome atual da conta é preservado."""
        make_whatsapp_account(self.alice, "loja", name="Loja do centro")
        with evolution_state("open"):
            self.register(instance="loja", key="chave-nova-999")
        self.assertEqual(SocialAccount.objects.get().name, "Loja do centro")

    # ---- AC-4 ------------------------------------------------------------
    @override_settings(EVOLUTION_API_URL="")
    def test_AC_4_not_configured_shows_the_notice_and_rejects_the_post(self):
        """AC-4: sem URL, a tela avisa, o cadastro fica indisponível e o POST não grava nem chama a Evolution."""
        page = self.client.get(reverse("social:accounts"))
        self.assertContains(page, "Integração com o WhatsApp não configurada")
        form = self.client.get(reverse(NEW))
        self.assertContains(form, "Integração com o WhatsApp não configurada")
        with evolution_state("open") as state:
            response = self.register(follow=True)
            state.assert_not_called()
        self.assertEqual(SocialAccount.objects.count(), 0)
        self.assertContains(response, "Integração com o WhatsApp não configurada")

    @override_settings(EVOLUTION_API_URL="http://evo.exemplo.host")
    def test_AC_4_http_url_counts_as_not_configured(self):
        """AC-4: URL HTTP (não HTTPS) é tratada como não configurada."""
        self.assertContains(self.client.get(reverse("social:accounts")), "Integração com o WhatsApp não configurada")

    def test_AC_4_facebook_and_threads_buttons_are_unaffected(self):
        """AC-4: com a Evolution configurada o botão de WhatsApp existe, e os outros continuam."""
        page = self.client.get(reverse("social:accounts"))
        self.assertContains(page, reverse(NEW))
        self.assertContains(page, reverse("social:facebook_connect"))  # spec 0017: a tela virou a central de conexões
        self.assertContains(page, reverse("social:threads_connect"))
        self.assertNotContains(page, "Integração com o WhatsApp não configurada")

    # ---- AC-5 ------------------------------------------------------------
    def test_AC_5_lists_the_account_with_instance_and_status_without_the_key(self):
        """AC-5: a lista mostra a plataforma, o nome da instância e o status; nunca a chave."""
        make_whatsapp_account(self.alice, "loja", name="Loja do centro", key=INSTANCE_KEY)
        response = self.client.get(reverse("social:accounts"))
        self.assertContains(response, "WhatsApp (Status)")
        self.assertContains(response, "Loja do centro")
        self.assertContains(response, "instância loja")
        self.assertContains(response, "Conexão ativa")  # spec 0017: a tela virou a central de conexões
        self.assertNotContains(response, INSTANCE_KEY)
        self.assertNotContains(response, "access_token_enc")

    def test_AC_5_reauth_account_offers_to_update_the_key_not_oauth(self):
        """AC-5: conta em Reconexão necessária oferece atualizar a chave (cadastro), não o OAuth da Meta."""
        make_whatsapp_account(self.alice, "loja", status=SocialAccount.Status.NEEDS_REAUTH)
        response = self.client.get(reverse("social:accounts"))
        self.assertContains(response, "Reconexão necessária")
        self.assertContains(response, f"{reverse(NEW)}?instance=loja")

    def test_AC_5_check_open_marks_the_account_active(self):
        """AC-5: Verificar com a instância `open` → conta ativa."""
        account = make_whatsapp_account(self.alice, "loja", status=SocialAccount.Status.NEEDS_REAUTH)
        with evolution_state("open") as state:
            response = self.client.post(reverse("social:account_check", args=[account.pk]), follow=True)
        account.refresh_from_db()
        self.assertEqual(account.status, SocialAccount.Status.ACTIVE)
        self.assertIsNotNone(account.last_checked_at)
        self.assertEqual(state.call_args.args[:2], ("loja", "chave-da-loja"))
        self.assertContains(response, "está conectada e funcionando")

    def test_AC_5_check_not_open_or_refused_key_needs_reauth(self):
        """AC-5: Verificar com estado ≠ `open`, chave recusada ou instância inexistente → Reconexão necessária."""
        scenarios = [dict(state="close"), dict(error_code="auth", error_status=401), dict(error_code="not_found", error_status=404)]
        for kwargs in scenarios:
            with self.subTest(**kwargs):
                account = make_whatsapp_account(self.alice, "loja")
                SocialAccount.objects.filter(pk=account.pk).update(status=SocialAccount.Status.ACTIVE)
                with evolution_state(**kwargs):
                    response = self.client.post(reverse("social:account_check", args=[account.pk]), follow=True)
                account.refresh_from_db()
                self.assertEqual(account.status, SocialAccount.Status.NEEDS_REAUTH)
                self.assertContains(response, "Reconexão necessária")
                self.assertNotIn("texto cru", account.last_error)
                account.delete()

    def test_AC_5_check_with_transient_failure_keeps_the_status(self):
        """AC-5: falha transitória ao verificar (timeout/rede/5xx) mantém o status e avisa para tentar depois."""
        account = make_whatsapp_account(self.alice, "loja")
        with evolution_state(error_code="timeout"):
            response = self.client.post(reverse("social:account_check", args=[account.pk]), follow=True)
        account.refresh_from_db()
        self.assertEqual(account.status, SocialAccount.Status.ACTIVE)
        self.assertContains(response, "Não foi possível verificar agora")

    @override_settings(EVOLUTION_API_URL="")
    def test_AC_5_check_when_not_configured_does_not_call_the_evolution(self):
        """AC-5/AC-4: sem configuração, Verificar avisa e não chama a Evolution."""
        account = make_whatsapp_account(self.alice, "loja")
        with evolution_state("open") as state:
            response = self.client.post(reverse("social:account_check", args=[account.pk]), follow=True)
            state.assert_not_called()
        self.assertContains(response, "Integração com o WhatsApp não configurada")

    def test_AC_5_disconnect_removes_the_account_and_keeps_history(self):
        """AC-5: Desconectar apaga a conta; o alvo do histórico continua, sem conta (snapshot do nome)."""
        account = make_whatsapp_account(self.alice, "loja", name="Loja do centro")
        pub = Publication.objects.create(owner=self.alice, text="Olá")
        target = PublicationTarget.objects.create(
            publication=pub, account=account, page_external_id="loja", page_name="Loja do centro", platform=WA,
        )
        response = self.client.post(reverse("social:account_disconnect", args=[account.pk]), follow=True)
        self.assertContains(response, "foi desconectada")
        self.assertFalse(SocialAccount.objects.filter(pk=account.pk).exists())
        target.refresh_from_db()
        self.assertIsNone(target.account)
        self.assertEqual(target.page_name, "Loja do centro")
        self.assertFalse(target.is_retryable)

    # ---- AC-16 -----------------------------------------------------------
    def test_AC_16_other_users_accounts_are_invisible_and_untouchable(self):
        """AC-16: lista, verificar e desconectar só funcionam para as próprias contas (404 nas de outros)."""
        theirs = make_whatsapp_account(self.bob, "loja-do-bob", name="Loja do Bob")
        self.assertNotContains(self.client.get(reverse("social:accounts")), "Loja do Bob")
        with evolution_state("open") as state:
            self.assertEqual(self.client.post(reverse("social:account_check", args=[theirs.pk])).status_code, 404)
            state.assert_not_called()
        self.assertEqual(self.client.post(reverse("social:account_disconnect", args=[theirs.pk])).status_code, 404)
        self.assertTrue(SocialAccount.objects.filter(pk=theirs.pk).exists())

    def test_AC_16_same_instance_name_for_two_users_creates_two_accounts(self):
        """AC-16: o mesmo nome de instância cadastrado por dois usuários gera duas contas, cada uma com a sua chave."""
        make_whatsapp_account(self.bob, "loja", key="chave-do-bob")
        with evolution_state("open"):
            self.register(instance="loja", key="chave-da-alice")
        mine = SocialAccount.objects.get(owner=self.alice)
        theirs = SocialAccount.objects.get(owner=self.bob)
        self.assertEqual((mine.get_token(), theirs.get_token()), ("chave-da-alice", "chave-do-bob"))

    def test_AC_16_anonymous_users_are_redirected_to_login(self):
        """AC-16: sem login, a tela e o POST de cadastro redirecionam para a entrada e nada é gravado."""
        self.client.logout()
        self.assertEqual(self.client.get(reverse(NEW)).status_code, 302)
        with evolution_state("open") as state:
            self.assertEqual(self.register(follow=False).status_code, 302)
            state.assert_not_called()
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_AC_16_only_post_is_accepted_for_account_actions(self):
        """AC-16: o cadastro exige POST com CSRF para gravar (GET só exibe o formulário)."""
        response = self.client.get(reverse(NEW))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SocialAccount.objects.count(), 0)

    # ---- AC-14 -----------------------------------------------------------
    def test_AC_14_logs_and_messages_never_contain_the_key_or_instance(self):
        """AC-14: o cadastro e a verificação não registram chave nem nome da instância."""
        with evolution_state("open"), self.assertLogs("apps.social.meta", level=logging.INFO) as logs:
            self.register(instance="minha-loja")
        self.assertIn("whatsapp_account_registered", "\n".join(logs.output))
        for secret in (INSTANCE_KEY, "minha-loja"):
            self.assertNotIn(secret, "\n".join(logs.output))

    def test_AC_14_host_called_is_always_the_configured_one(self):
        """AC-14: o cliente criado pelo cadastro usa o host do servidor (o usuário só informa o nome da instância)."""
        captured = {}
        original = EvolutionClient.__init__

        def spy(self_, **kwargs):
            captured.update(kwargs)
            original(self_, **kwargs)

        session = mock.Mock()
        session.request.return_value = mock.Mock(status_code=200, json=lambda: {"instance": {"state": "open"}})
        with mock.patch.object(EvolutionClient, "__init__", spy), mock.patch("requests.Session", return_value=session):
            self.register(instance="minha-loja")
        self.assertEqual(captured["base_url"], "https://evo.exemplo.host")
        url = session.request.call_args.args[1]
        self.assertEqual(url, "https://evo.exemplo.host/instance/connectionState/minha-loja")
