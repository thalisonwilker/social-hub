"""Spec 0017 — central de conexões em /contas/ (um `test_AC_N_*` por critério testável pelo HTML)."""
import re
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.social.models import Publication, PublicationTarget, SocialAccount
from apps.social.services.meta import GraphClient

from .evolution_helpers import EVOLUTION_SETTINGS, make_whatsapp_account
from .helpers import PAGE_TOKEN_1, VALID_META_SETTINGS
from .test_instagram_model import make_instagram, make_page
from .threads_helpers import THREADS_SETTINGS

ALL_SETTINGS = {**VALID_META_SETTINGS, **THREADS_SETTINGS, **EVOLUTION_SETTINGS}
URL = "/contas/"


def make_threads(owner, external_id="900", username="maria", **kwargs):
    account = SocialAccount(owner=owner, platform="threads", external_id=external_id, name=username.title(),
                            username=username, token_expires_at=timezone.now() + timedelta(days=50), **kwargs)
    account.set_token("threads-token")
    account.save()
    return account


def tag(html, element_id):
    """A tag de abertura do elemento com esse id (para conferir atributos)."""
    match = re.search(rf'<[^>]*\bid="{re.escape(element_id)}"[^>]*>', html, re.S)
    assert match, element_id
    return match.group(0)


def panel(html, slug):
    start = html.index(f'id="hub-panel-{slug}"')
    end = html.find('role="tabpanel" id="hub-panel-', start + 1)
    return html[start:end if end != -1 else len(html)]


@override_settings(**ALL_SETTINGS)
class ConnectionsHubTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice", password="x")
        cls.bob = User.objects.create_user("bob", password="x")

    def setUp(self):
        self.client.force_login(self.alice)

    def page(self, query=""):
        response = self.client.get(URL + query)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def selected(self, html):
        return re.findall(r'data-hub-tab="(\w+)"', html), [
            slug for slug in ("facebook", "instagram", "threads", "whatsapp")
            if 'aria-selected="true"' in tag(html, f"hub-tab-{slug}")
        ]

    # ---- AC-1 ------------------------------------------------------------
    def test_AC_1_icons_column_in_fixed_order_and_one_panel(self):
        html = self.page()
        order, _ = self.selected(html)
        self.assertEqual(order, ["facebook", "instagram", "threads", "whatsapp"])
        self.assertIn('class="hub-panel"', html)

    # ---- AC-2 (matriz) ---------------------------------------------------
    def test_AC_2_icon_state_follows_the_decision_matrix(self):
        make_page(self.alice)  # Facebook: ativa
        make_threads(self.alice, status=SocialAccount.Status.NEEDS_REAUTH)
        make_threads(self.alice, "901", "joao")  # uma ativa + uma reconexão → âmbar
        html = self.page()
        self.assertIn('data-state="connected"', tag(html, "hub-tab-facebook"))
        self.assertIn('data-state="disconnected"', tag(html, "hub-tab-instagram"))
        self.assertIn('data-state="needs_reauth"', tag(html, "hub-tab-threads"))
        self.assertIn('data-state="disconnected"', tag(html, "hub-tab-whatsapp"))

    # ---- AC-3 ------------------------------------------------------------
    def test_AC_3_each_icon_has_a_tooltip_with_the_network_name(self):
        html = self.page()
        for label in ("Facebook", "Instagram", "Threads", "WhatsApp"):
            self.assertIn(f'<span class="hub-tip" aria-hidden="true">{label}</span>', html)

    # ---- AC-4 ------------------------------------------------------------
    def test_AC_4_without_accounts_facebook_is_selected(self):
        self.assertEqual(self.selected(self.page())[1], ["facebook"])

    def test_AC_4_first_connected_network_is_selected(self):
        make_threads(self.alice)
        make_whatsapp_account(self.alice)
        self.assertEqual(self.selected(self.page())[1], ["threads"])

    def test_AC_4_query_param_selects_the_network(self):
        make_threads(self.alice)
        html = self.page("?rede=whatsapp")
        self.assertEqual(self.selected(html)[1], ["whatsapp"])
        self.assertNotIn(" hidden", tag(html, "hub-panel-whatsapp"))
        self.assertIn(" hidden", tag(html, "hub-panel-threads"))

    def test_AC_4_unknown_param_falls_back_without_error(self):
        make_threads(self.alice)
        for query in ("?rede=tiktok", "?rede=", "?rede=%3Cscript%3E"):
            self.assertEqual(self.selected(self.page(query))[1], ["threads"], query)

    # ---- AC-5 (sem JS) ---------------------------------------------------
    def test_AC_5_icons_are_links_and_page_loads_the_switch_script(self):
        html = self.page()
        for slug in ("facebook", "instagram", "threads", "whatsapp"):
            self.assertIn(f'href="?rede={slug}"', tag(html, f"hub-tab-{slug}"))
        self.assertIn("js/connections.js", html)

    # ---- AC-6 ------------------------------------------------------------
    def test_AC_6_connected_panel_shows_header_facts_sync_permissions_and_actions(self):
        page = make_page(self.alice, name="Garimpei gostei")
        SocialAccount.objects.filter(pk=page.pk).update(
            category="Loja", followers_count=12345, granted_tasks=["CREATE_CONTENT", "MANAGE"],
            last_checked_at=timezone.now(),
        )
        pub = Publication.objects.create(owner=self.alice, text="x")
        for i, status in enumerate(["published", "published", "failed"]):
            PublicationTarget.objects.create(publication=pub if i == 0 else Publication.objects.create(owner=self.alice, text="y"),
                                             account=page, page_external_id="1", page_name="G", status=status)
        html = panel(self.page(), "facebook")
        self.assertIn("Garimpei gostei", html)
        self.assertIn("Conexão ativa", html)
        self.assertIn("Página do Facebook", html)
        self.assertIn("<dd class=\"truncate\">Loja</dd>", html)
        self.assertIn("12.345", html)
        self.assertRegex(html, r"<dt>Publicações</dt>\s*<dd>2</dd>")
        self.assertIn(timezone.localtime(page.connected_at).strftime("%d/%m/%Y"), html)
        self.assertIn("Última sincronização", html)
        self.assertNotIn("Nunca", html)
        self.assertIn("CREATE_CONTENT", html)
        for action in ("Atualizar informações", "Reconectar", "Desconectar"):
            self.assertIn(action, html)
        self.assertNotIn(PAGE_TOKEN_1, html)
        self.assertNotIn("page-token", html)

    def test_AC_6_unknown_values_show_dash_and_never(self):
        make_whatsapp_account(self.alice, "loja", key="CHAVE-SECRETA")
        html = panel(self.page("?rede=whatsapp"), "whatsapp")
        self.assertIn("instância loja", html)
        self.assertRegex(html, r"<dt>Seguidores</dt>\s*<dd>—</dd>")
        self.assertIn("Nunca", html)
        self.assertRegex(html, r"Permissões:</span>\s*<span>—</span>")
        self.assertNotIn("CHAVE-SECRETA", html)

    def test_AC_6_user_field_per_platform(self):
        fb = make_page(self.alice, name="Loja")
        make_instagram(self.alice, fb, username="loja_ig")
        make_threads(self.alice, username="maria")
        html = self.page()
        self.assertIn("@loja_ig · via Página Loja", panel(html, "instagram"))
        self.assertIn("@maria", panel(html, "threads"))

    def test_AC_6_reauth_account_shows_warning_status(self):
        make_page(self.alice)
        SocialAccount.objects.update(status=SocialAccount.Status.NEEDS_REAUTH)
        self.assertIn("Reconexão necessária", panel(self.page(), "facebook"))

    def test_AC_6_only_own_accounts(self):
        make_page(self.bob, name="Loja do Bob")
        self.assertNotIn("Loja do Bob", self.page())

    # ---- AC-7 ------------------------------------------------------------
    def test_AC_7_two_accounts_get_a_compact_list_first_by_name_visible(self):
        make_page(self.alice, "2", name="Zeta")
        a = make_page(self.alice, "1", name="alfa")
        z = SocialAccount.objects.get(name="Zeta")
        html = panel(self.page(), "facebook")
        self.assertIn("data-hub-account-list", html)
        self.assertIn('aria-selected="true"', tag(html, f"hub-acct-tab-{a.pk}"))
        self.assertNotIn(" hidden", tag(html, f"hub-acct-{a.pk}"))
        self.assertIn(" hidden", tag(html, f"hub-acct-{z.pk}"))

    def test_AC_7_single_account_has_no_list(self):
        make_page(self.alice)
        self.assertNotIn("data-hub-account-list", panel(self.page(), "facebook"))

    # ---- AC-8 ------------------------------------------------------------
    def test_AC_8_disconnected_panels_offer_connect_with_the_right_flow(self):
        html = self.page()
        expectations = {
            "facebook": f'action="{reverse("social:facebook_connect")}"',
            "instagram": f'action="{reverse("social:facebook_connect")}"',
            "threads": f'action="{reverse("social:threads_connect")}"',
            "whatsapp": f'href="{reverse("social:whatsapp_new")}"',
        }
        for slug, target in expectations.items():
            body = panel(html, slug)
            self.assertIn("Nenhuma conta vinculada", body, slug)
            self.assertIn("Conectar conta", body, slug)
            self.assertIn(target, body, slug)
        self.assertIn("O Instagram é conectado pela sua Página do Facebook.", panel(html, "instagram"))

    def test_AC_8_not_configured_disables_connect(self):
        cases = {
            "facebook": ({"META_APP_SECRET": ""}, "Integração com a Meta não configurada"),
            "threads": ({"THREADS_APP_ID": ""}, "Integração com o Threads não configurada"),
            "whatsapp": ({"EVOLUTION_API_URL": ""}, "Integração com o WhatsApp não configurada"),
        }
        for slug, (overrides, message) in cases.items():
            with self.subTest(slug), override_settings(**overrides):
                body = panel(self.page(), slug)
                self.assertIn(message, body)
                button = body[body.index("<button"):body.index("</button>")]
                self.assertIn("disabled", button)

    # ---- AC-10 -----------------------------------------------------------
    def test_AC_10_primary_button_follows_the_matrix(self):
        make_page(self.alice)
        active = panel(self.page(), "facebook")
        self.assertRegex(active, r'class="btn btn-primary"><i data-lucide="refresh-cw"[^>]*></i>Atualizar informações')
        self.assertRegex(active, r'class="btn "\s*><i data-lucide="link"[^>]*></i>Reconectar')
        SocialAccount.objects.update(status=SocialAccount.Status.NEEDS_REAUTH)
        reauth = panel(self.page(), "facebook")
        self.assertRegex(reauth, r'class="btn btn-primary"\s*><i data-lucide="link"[^>]*></i>Reconectar')
        with override_settings(META_APP_SECRET=""):
            off = panel(self.page(), "facebook")
        self.assertRegex(off, r'Reconectar')
        self.assertRegex(off, r'<button type="submit" class="btn btn-primary" disabled')

    def test_AC_10_whatsapp_reconnect_goes_to_the_instance_form(self):
        make_whatsapp_account(self.alice, "loja")
        self.assertIn(f'href="{reverse("social:whatsapp_new")}?instance=loja"', panel(self.page(), "whatsapp"))

    # ---- AC-11 -----------------------------------------------------------
    def test_AC_11_disconnect_keeps_confirmation_and_returns_to_the_network(self):
        account = make_threads(self.alice)
        html = panel(self.page(), "threads")
        self.assertIn("data-confirm=", html)
        response = self.client.post(reverse("social:account_disconnect", args=[account.pk]))
        self.assertRedirects(response, URL + "?rede=threads", fetch_redirect_response=False)
        self.assertFalse(SocialAccount.objects.filter(pk=account.pk).exists())

    def test_AC_11_facebook_confirmation_mentions_linked_instagram(self):
        make_page(self.alice)
        self.assertIn("O Instagram vinculado a esta Página também será desconectado.", panel(self.page(), "facebook"))

    def test_AC_11_other_users_get_404(self):
        account = make_threads(self.bob)
        for name in ("social:account_disconnect", "social:account_check"):
            self.assertEqual(self.client.post(reverse(name, args=[account.pk])).status_code, 404)

    # ---- AC-13 -----------------------------------------------------------
    def test_AC_13_tablist_semantics(self):
        make_page(self.alice)
        html = self.page()
        self.assertIn('role="tablist" aria-label="Redes sociais"', html)
        fb = tag(html, "hub-tab-facebook")
        self.assertIn('role="tab"', fb)
        self.assertIn('aria-label="Facebook — conectada"', fb)
        self.assertIn('aria-controls="hub-panel-facebook"', fb)
        self.assertIn('tabindex="0"', fb)
        ig = tag(html, "hub-tab-instagram")
        self.assertIn('aria-label="Instagram — desconectada"', ig)
        self.assertIn('tabindex="-1"', ig)
        self.assertIn('aria-labelledby="hub-tab-facebook"', tag(html, "hub-panel-facebook"))
        SocialAccount.objects.update(status=SocialAccount.Status.NEEDS_REAUTH)
        self.assertIn('aria-label="Facebook — reconexão necessária"', tag(self.page(), "hub-tab-facebook"))


@override_settings(**ALL_SETTINGS)
class AccountCheckReturnsToNetworkTests(TestCase):
    """AC-9: depois de Atualizar informações, volta para a mesma rede."""

    def test_AC_9_check_redirects_to_the_network(self):
        user = get_user_model().objects.create_user("alice", password="x")
        self.client.force_login(user)
        page = make_page(user)
        with mock.patch.object(GraphClient, "get_page", return_value={"id": "1"}), \
             mock.patch.object(GraphClient, "get_followers_count", return_value=10):
            response = self.client.post(reverse("social:account_check", args=[page.pk]))
        self.assertRedirects(response, URL + "?rede=facebook", fetch_redirect_response=False)
