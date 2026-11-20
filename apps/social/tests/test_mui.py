"""Spec 0012 — interface MUI: o HTML do servidor carrega o bundle e traz os ganchos que o elevador reconhece."""
import re
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from django.test import override_settings

from apps.social.models import Profile

from .helpers import VALID_META_SETTINGS

ROOT = Path(__file__).resolve().parents[3]


@override_settings(**VALID_META_SETTINGS)
class MuiInterfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice", password="pw12345!")
        cls.profile = Profile.objects.create(owner=cls.user, name="Loja")

    def setUp(self):
        self.client.force_login(self.user)

    def assert_bundle_before_app(self, response):
        html = response.content.decode()
        self.assertIn("dist/js/mui.js", html)
        self.assertLess(html.index("dist/js/mui.js"), html.index("js/app.js"))

    def test_AC_1_bundle_loaded_on_every_kind_of_page(self):
        self.client.logout()
        self.assert_bundle_before_app(self.client.get(reverse("accounts:login")))
        self.client.force_login(self.user)
        for name, args in (
            ("social:profile_select", []),
            ("social:profile_new", []),
            ("social:profile_connect", [self.profile.pk]),
            ("social:accounts", []),
            ("social:posts", []),
            ("social:post_new", []),
            ("accounts:profile", []),
            ("social:calendar", []),
        ):
            self.assert_bundle_before_app(self.client.get(reverse(name, args=args)))
        self.client.post(reverse("social:profile_enter", args=[self.profile.pk]))
        self.assert_bundle_before_app(self.client.get(reverse("dashboard:index")))

    def test_AC_2_server_html_keeps_forms_csrf_and_fields(self):
        html = self.client.get(reverse("social:profile_connect", args=[self.profile.pk])).content.decode()
        self.assertIn("csrfmiddlewaretoken", html)
        self.assertIn('action="%s"' % reverse("social:profile_done", args=[self.profile.pk]), html)
        login = self.client.get(reverse("accounts:profile")).content.decode()
        self.assertIn('method="post" action="%s"' % reverse("accounts:logout"), login)

    def test_AC_4_shell_hooks_present(self):
        html = self.client.get(reverse("social:accounts")).content.decode()
        self.assertIn('data-mui="sidebar"', html)
        self.assertIn('data-mui="header"', html)
        self.assertIn("data-user-link", html)

    def test_AC_4_profile_chip_hooks_when_profile_active(self):
        self.client.post(reverse("social:profile_enter", args=[self.profile.pk]))
        html = self.client.get(reverse("social:accounts")).content.decode()
        self.assertIn("data-profile-chip", html)
        self.assertIn('data-name="Loja"', html)

    def test_AC_7_profile_screens_use_mui_hooks(self):
        select = self.client.get(reverse("social:profile_select")).content.decode()
        self.assertIn('data-mui="tile"', select)
        self.assertIn('data-mui-theme="dark"', select)
        wizard = self.client.get(reverse("social:profile_connect", args=[self.profile.pk])).content.decode()
        self.assertIn('data-mui="stepper"', wizard)
        self.assertEqual(wizard.count('data-mui="tile"'), 6)

    def test_AC_5_confirmation_still_declared_on_the_form(self):
        from .test_profiles import make_account

        account = make_account(self.user, self.profile)
        html = self.client.get(reverse("social:accounts")).content.decode()
        self.assertRegex(html, r'<form[^>]*action="%s"[^>]*data-confirm=' % reverse("social:account_disconnect", args=[account.pk]))

    def test_AC_3_controls_keep_native_hooks_for_the_lifter(self):
        from .test_profiles import make_account

        make_account(self.user, self.profile)
        html = self.client.get(reverse("social:post_new")).content.decode()
        self.assertRegex(html, r'class="[^"]*\bbtn\b')
        self.assertIn("data-confirm", html)

    def test_AC_8_build_pipeline_produces_the_bundle(self):
        scripts = (ROOT / "package.json").read_text()
        self.assertIn("build:js", scripts)
        self.assertTrue((ROOT / "frontend/mui/index.jsx").exists())
        self.assertRegex(scripts, r'"build":\s*"[^"]*build:js')
        self.assertIn("npm run build", (ROOT / "Dockerfile").read_text())

    def test_AC_6_dark_regions_are_marked(self):
        self.client.logout()
        login = self.client.get(reverse("accounts:login")).content.decode()
        self.assertIn('data-mui-theme="dark"', login)
        self.assertTrue(re.search(r"data-theme-toggle", login))
