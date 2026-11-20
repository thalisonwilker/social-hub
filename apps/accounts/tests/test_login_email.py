from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase
from django.urls import reverse

from .helpers import LOGIN_URL, SIGNUP_URL, STRONG_PASSWORD, login_data, signup_data

User = get_user_model()


class EmailBackendTests(TestCase):
    """Spec 0013 AC-8 e spec 0014 AC-4: login só por e-mail."""

    def test_AC_4_signup_account_any_case(self):
        self.client.post(SIGNUP_URL, signup_data(email="fulano@exemplo.com"))
        response = self.client.post(LOGIN_URL, login_data("FULANO@exemplo.com", STRONG_PASSWORD))
        self.assertRedirects(response, reverse("social:profile_select"), fetch_redirect_response=False)

    def test_AC_4_legacy_account_enters_by_email_field(self):
        User.objects.create_user("admin", email="admin@example.com", password="s3nha-antiga")
        self.assertIsNotNone(authenticate(username="ADMIN@example.com", password="s3nha-antiga"))

    def test_AC_4_username_without_at_never_authenticates(self):
        User.objects.create_user("admin", email="admin@example.com", password="s3nha-antiga")
        self.assertIsNone(authenticate(username="admin", password="s3nha-antiga"))
        response = self.client.post(LOGIN_URL, login_data("admin", "s3nha-antiga"))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Informe um e-mail válido.", status_code=400)

    def test_AC_4_email_in_more_than_one_legacy_account_does_not_authenticate(self):
        User.objects.create_user("a1", email="dup@x.com", password="pw")
        User.objects.create_user("a2", email="DUP@x.com", password="pw")
        self.assertIsNone(authenticate(username="dup@x.com", password="pw"))

    def test_AC_4_username_match_wins_over_email_field(self):
        own = User.objects.create_user("ana@x.com", email="ana@x.com", password="pw-certa")
        User.objects.create_user("velho", email="ana@x.com", password="outra")
        self.assertEqual(authenticate(username="Ana@X.com", password="pw-certa"), own)

    def test_AC_2_inactive_user_cannot_login(self):
        User.objects.create_user("x@y.com", email="x@y.com", password=STRONG_PASSWORD, is_active=False)
        self.assertIsNone(authenticate(username="x@y.com", password=STRONG_PASSWORD))

    def test_login_label_is_email(self):
        self.assertContains(self.client.get(LOGIN_URL), ">E-mail</label>")
