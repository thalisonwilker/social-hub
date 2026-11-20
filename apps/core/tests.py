from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.tests.helpers import login_data


class SmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("tester", email="tester@exemplo.com", password="s3nha-forte-123")

    def test_health_is_public(self):
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_pages_require_login(self):
        for name in ("dashboard:index", "social:accounts", "social:posts", "social:calendar", "accounts:profile"):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, f"{reverse('accounts:login')}?next={reverse(name)}", msg_prefix=name)

    def test_login_page_is_public(self):
        self.assertEqual(self.client.get(reverse("accounts:login")).status_code, 200)

    def test_login_and_pages_render(self):
        self.assertTrue(self.client.login(username="tester@exemplo.com", password="s3nha-forte-123"))
        for name in ("dashboard:index", "social:accounts", "social:posts", "social:calendar", "accounts:profile", "accounts:password_change"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_login_flow_redirects_to_profile_select(self):
        response = self.client.post(
            reverse("accounts:login"), login_data("tester@exemplo.com", "s3nha-forte-123")
        )
        self.assertRedirects(response, reverse("social:profile_select"))  # spec 0011, AC-1

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertRedirects(
            self.client.post(reverse("accounts:logout")), reverse("accounts:login")
        )
