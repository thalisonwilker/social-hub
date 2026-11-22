from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services.meta import MetaApiError
from apps.social.services.threads import ThreadsClient

from .threads_helpers import LONG, THREADS_SETTINGS, make_threads_account


@override_settings(**THREADS_SETTINGS)
class ThreadsAccountsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice", password="x")
        cls.bob = User.objects.create_user("bob", password="x")

    def setUp(self):
        self.client.force_login(self.alice)

    def accounts_page(self):
        return self.client.get(reverse("social:accounts"))

    def check(self, account):
        return self.client.post(reverse("social:account_check", args=[account.pk]), follow=True)

    # ---- AC-9 ------------------------------------------------------------
    def test_AC_9_lists_profile_with_username_platform_and_validity_without_token(self):
        """AC-9: mostra @usuário, plataforma, status e validade; nunca o token."""
        acc = make_threads_account(self.alice, days_left=10)
        response = self.accounts_page()
        self.assertContains(response, "Perfil do Threads")
        self.assertContains(response, "@maria")
        self.assertContains(response, "token expira em 9 dia(s)")  # 10 dias - frações do instante do teste
        self.assertContains(response, "Conexão ativa")  # spec 0017: a tela virou a central de conexões
        self.assertNotContains(response, "threads-long-token")
        self.assertNotContains(response, acc.access_token_enc)

    def test_AC_9_facebook_pages_have_no_validity_text(self):
        """AC-9: Páginas do Facebook (token que não expira) não mostram validade."""
        page = SocialAccount(owner=self.alice, platform="facebook_page", external_id="1", name="Minha Página")
        page.set_token("t")
        page.save()
        response = self.accounts_page()
        self.assertContains(response, "Minha Página")
        self.assertNotContains(response, "token expira em")

    def test_AC_9_expired_token_becomes_needs_reauth_locally_without_network(self):
        """AC-9: token vencido aparece como Reconexão necessária, atualizado só no banco (sem chamadas à Meta)."""
        acc = make_threads_account(self.alice, days_left=-1)
        with mock.patch("requests.Session.request") as http:
            response = self.accounts_page()
        http.assert_not_called()
        acc.refresh_from_db()
        self.assertEqual(acc.status, SocialAccount.Status.NEEDS_REAUTH)
        self.assertContains(response, "Reconexão necessária")

    def test_AC_9_only_own_accounts_are_listed(self):
        """AC-9: perfis de outros usuários não aparecem."""
        make_threads_account(self.alice, "900", username="maria")
        make_threads_account(self.bob, "901", username="bob_threads")
        response = self.accounts_page()
        self.assertContains(response, "@maria")
        self.assertNotContains(response, "bob_threads")

    def test_AC_9_reconnect_button_points_to_the_right_platform(self):
        """AC-9: Reconectar de um perfil do Threads usa a rota do Threads; o de uma Página usa a do Facebook."""
        make_threads_account(self.alice, "900", status=SocialAccount.Status.NEEDS_REAUTH)
        page = SocialAccount(owner=self.alice, platform="facebook_page", external_id="1", name="Pág",
                             status=SocialAccount.Status.NEEDS_REAUTH)
        page.set_token("t")
        page.save()
        html = self.accounts_page().content.decode()
        # spec 0017: rede conectada mostra só o Reconectar (o "Conectar conta" é do painel de rede desconectada)
        self.assertEqual(html.count(f'action="{reverse("social:threads_connect")}"'), 1)
        self.assertEqual(html.count(f'action="{reverse("social:facebook_connect")}"'), 2)  # Reconectar + "Conectar conta" do Instagram

    # ---- AC-10 -----------------------------------------------------------
    def test_AC_10_verify_refreshes_when_due_then_reads_the_profile(self):
        """AC-10: Verificar aplica a renovação devida e lê o perfil; sucesso → active e last_checked_at."""
        acc = make_threads_account(self.alice, days_left=5, status=SocialAccount.Status.NEEDS_REAUTH, token="antigo")
        with mock.patch.object(ThreadsClient, "refresh_token", return_value={"access_token": "novo", "expires_in": 5184000}) as refresh, \
             mock.patch.object(ThreadsClient, "get_profile", return_value={"id": "900"}) as profile:
            response = self.check(acc)
        refresh.assert_called_once_with("antigo")
        profile.assert_called_once_with("900", "novo")
        acc.refresh_from_db()
        self.assertEqual((acc.status, acc.last_error), (SocialAccount.Status.ACTIVE, ""))
        self.assertIsNotNone(acc.last_checked_at)
        self.assertEqual(acc.get_token(), "novo")
        self.assertContains(response, "conectada e funcionando")

    def test_AC_10_verify_without_renewal_only_reads_the_profile(self):
        """AC-10: com token longe da expiração não renova, só lê o perfil."""
        acc = make_threads_account(self.alice, days_left=50)
        with mock.patch.object(ThreadsClient, "refresh_token") as refresh, \
             mock.patch.object(ThreadsClient, "get_profile", return_value={"id": "900"}):
            self.check(acc)
        refresh.assert_not_called()

    def test_AC_10_token_error_on_profile_marks_needs_reauth(self):
        """AC-10: erro de token ao ler o perfil → needs_reauth com last_error resumido."""
        acc = make_threads_account(self.alice, days_left=50)
        with mock.patch.object(ThreadsClient, "get_profile", side_effect=MetaApiError("x", code=190)):
            response = self.check(acc)
        acc.refresh_from_db()
        self.assertEqual((acc.status, acc.last_error), (SocialAccount.Status.NEEDS_REAUTH, "Meta erro 190"))
        self.assertContains(response, "Reconexão necessária")

    def test_AC_10_other_errors_keep_the_status(self):
        """AC-10: erro de rede ou limite → status inalterado e aviso 'não foi possível verificar agora'."""
        for error in (MetaApiError("x", code="network"), MetaApiError("x", code=4, status=429)):
            acc = make_threads_account(self.alice, f"e{error.code}", days_left=50)
            with mock.patch.object(ThreadsClient, "get_profile", side_effect=error):
                response = self.check(acc)
            acc.refresh_from_db()
            self.assertEqual(acc.status, SocialAccount.Status.ACTIVE)
            self.assertContains(response, "Não foi possível verificar agora")

    def test_AC_10_expired_token_is_reported_without_reading_the_profile(self):
        """AC-10: token já vencido → Reconexão necessária, sem chamar a API."""
        acc = make_threads_account(self.alice, days_left=-3)
        with mock.patch.object(ThreadsClient, "get_profile") as profile:
            response = self.check(acc)
        profile.assert_not_called()
        self.assertContains(response, "Reconexão necessária")
        acc.refresh_from_db()
        self.assertEqual(acc.status, SocialAccount.Status.NEEDS_REAUTH)

    @override_settings(THREADS_APP_ID="")
    def test_AC_10_verify_when_threads_is_not_configured(self):
        """AC-10: sem THREADS_* o Verificar avisa e não chama a API."""
        acc = make_threads_account(self.alice)
        with mock.patch.object(ThreadsClient, "get_profile") as profile:
            response = self.check(acc)
        profile.assert_not_called()
        self.assertContains(response, "Integração com o Threads não configurada")

    # ---- AC-11 -----------------------------------------------------------
    def test_AC_11_disconnect_deletes_the_account_and_keeps_history_snapshots(self):
        """AC-11: desconectar apaga conta e token; os alvos antigos mantêm o snapshot do nome."""
        acc = make_threads_account(self.alice)
        pub = Publication.objects.create(owner=self.alice, text="x")
        target = PublicationTarget.objects.create(
            publication=pub, account=acc, page_external_id="900", page_name="Maria", platform="threads")
        response = self.client.post(reverse("social:account_disconnect", args=[acc.pk]), follow=True)
        self.assertRedirects(response, reverse("social:accounts") + "?rede=threads")  # spec 0017: a tela virou a central de conexões
        self.assertContains(response, "foi desconectada")
        self.assertFalse(SocialAccount.objects.filter(pk=acc.pk).exists())
        target.refresh_from_db()
        self.assertIsNone(target.account)
        self.assertEqual((target.page_name, target.platform), ("Maria", "threads"))

    # ---- AC-26 -----------------------------------------------------------
    def test_AC_26_other_users_get_404_on_check_and_disconnect(self):
        """AC-26: o usuário B não verifica nem desconecta o perfil de A; nada muda."""
        acc = make_threads_account(self.alice)
        self.client.force_login(self.bob)
        for name in ("social:account_check", "social:account_disconnect"):
            with self.subTest(name), mock.patch.object(ThreadsClient, "get_profile") as profile:
                self.assertEqual(self.client.post(reverse(name, args=[acc.pk])).status_code, 404)
                profile.assert_not_called()
        self.assertTrue(SocialAccount.objects.filter(pk=acc.pk).exists())
