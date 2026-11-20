import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase
from django.urls import reverse

from apps.accounts import idempotency
from apps.accounts.models import SignupIdempotencyKey

from .helpers import SIGNUP_URL, signup_data

User = get_user_model()
LOGIN_URL = reverse("accounts:login")
SUCCESS = "Sua conta foi criada com sucesso! Faça login para continuar."  # spec 0015, AC-6
EXPIRED = "O formulário expirou. Revise os dados e envie novamente."


class SignupIdempotencyTests(TestCase):
    def test_AC_11_repeated_request_creates_one_user_and_repeats_success(self):
        data = signup_data()
        first = self.client.post(SIGNUP_URL, data)
        second = self.client.post(SIGNUP_URL, data, follow=True)
        self.assertRedirects(first, LOGIN_URL, fetch_redirect_response=False)
        self.assertRedirects(second, LOGIN_URL)
        self.assertContains(second, SUCCESS)
        self.assertNotContains(second, "Este e-mail já está cadastrado.")
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(SignupIdempotencyKey.objects.get().user, User.objects.get())

    def test_AC_11_many_repetitions(self):
        data = signup_data()
        for _ in range(5):
            self.client.post(SIGNUP_URL, data)
        self.assertEqual(User.objects.count(), 1)

    def test_AC_11_race_where_other_request_wins(self):
        """Duas requisições com a mesma chave validam juntas; a segunda esbarra na unicidade."""
        data = signup_data()
        key = idempotency.read_key(data["chave_idempotencia"])
        winner = User.objects.create_user("maria@exemplo.com", email="maria@exemplo.com", password="x")
        SignupIdempotencyKey.objects.create(key=key, user=winner)
        exists = mock.Mock(side_effect=[False, True])  # pré-checagem não viu; pós-checagem vê
        with mock.patch("apps.accounts.forms.email_taken", return_value=False), \
             mock.patch("apps.accounts.views.SignupIdempotencyKey.objects.filter") as flt:
            flt.return_value.exists = exists
            response = self.client.post(SIGNUP_URL, data, follow=True)
        self.assertContains(response, SUCCESS)
        self.assertEqual(User.objects.count(), 1)

    def test_AC_11_race_with_different_key_reports_email_taken(self):
        User.objects.create_user("maria@exemplo.com", email="maria@exemplo.com", password="x")
        with mock.patch("apps.accounts.forms.email_taken", return_value=False):
            response = self.client.post(SIGNUP_URL, signup_data())
        self.assertContains(response, "Este e-mail já está cadastrado.")
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(SignupIdempotencyKey.objects.count(), 0)

    def test_AC_11_invalid_data_does_not_register_key_and_issues_new_one(self):
        data = signup_data(accept_terms=None)
        response = self.client.post(SIGNUP_URL, data)
        self.assertEqual(SignupIdempotencyKey.objects.count(), 0)
        self.assertNotEqual(response.context["chave_idempotencia"], data["chave_idempotencia"])
        # Corrigido e reenviado com a mesma chave antiga, ainda funciona (não foi consumida).
        self.client.post(SIGNUP_URL, {**data, "accept_terms": "on"})
        self.assertEqual(User.objects.count(), 1)

    def test_AC_12_missing_invalid_or_expired_key(self):
        cases = {
            "ausente": None,
            "lixo": "abc",
            "adulterada": idempotency.issue_key()[:-2] + "xx",
            "outro salt": signing.dumps("0" * 32, salt="outro"),
        }
        for label, token in cases.items():
            with self.subTest(label):
                response = self.client.post(SIGNUP_URL, signup_data(chave_idempotencia=token))
                self.assertContains(response, EXPIRED)
                self.assertContains(response, 'value="maria@exemplo.com"')
                self.assertNotContains(response, "Quarto#Azul42")
                self.assertTrue(idempotency.read_key(response.context["chave_idempotencia"]))
        self.assertEqual(User.objects.count(), 0)

    def test_AC_12_key_older_than_two_hours(self):
        token = idempotency.issue_key()
        with mock.patch("django.core.signing.time.time", return_value=time.time() + 2 * 3600 + 5):
            response = self.client.post(SIGNUP_URL, signup_data(chave_idempotencia=token))
        self.assertContains(response, EXPIRED)
        self.assertEqual(User.objects.count(), 0)
