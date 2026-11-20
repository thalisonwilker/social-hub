from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .helpers import SIGNUP_URL, STRONG_PASSWORD, signup_data

User = get_user_model()
LOGIN_URL = reverse("accounts:login")


class LoginByEmailTests(TestCase):
    def test_AC_8_login_with_email_any_case(self):
        self.client.post(SIGNUP_URL, signup_data(email="fulano@exemplo.com"))
        response = self.client.post(LOGIN_URL, {"username": "FULANO@exemplo.com", "password": STRONG_PASSWORD})
        self.assertRedirects(response, reverse("social:profile_select"), fetch_redirect_response=False)

    def test_AC_8_wrong_password_shows_portuguese_error(self):
        User.objects.create_user("fulano@exemplo.com", email="fulano@exemplo.com", password=STRONG_PASSWORD)
        response = self.client.post(LOGIN_URL, {"username": "Fulano@exemplo.com", "password": "errada"})
        self.assertContains(response, "E-mail ou senha incorretos.")

    def test_AC_8_legacy_username_still_works(self):
        User.objects.create_user("admin", password="s3nha-antiga")
        response = self.client.post(LOGIN_URL, {"username": "admin", "password": "s3nha-antiga"})
        self.assertRedirects(response, reverse("social:profile_select"), fetch_redirect_response=False)

    def test_AC_8_inactive_user_cannot_login(self):
        User.objects.create_user("x@y.com", email="x@y.com", password=STRONG_PASSWORD, is_active=False)
        response = self.client.post(LOGIN_URL, {"username": "X@Y.com", "password": STRONG_PASSWORD})
        self.assertEqual(response.status_code, 200)

    def test_AC_8_label_is_email(self):
        self.assertContains(self.client.get(LOGIN_URL), ">E-mail</label>")
