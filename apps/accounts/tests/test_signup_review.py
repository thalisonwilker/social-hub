"""Spec 0015 — revisão pontual do cadastro."""

import unicodedata
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.forms import SignupForm
from apps.accounts.validators import validate_person_name

from .helpers import SIGNUP_URL, signup_data

User = get_user_model()
SUCCESS = "Sua conta foi criada com sucesso! Faça login para continuar."


class SignupReviewTests(TestCase):
    def test_AC_1_registrar_button_with_loading_markup(self):
        response = self.client.get(SIGNUP_URL)
        self.assertContains(response, "<span data-submit-label>Registrar</span>")
        self.assertContains(response, "data-loading")

    def test_AC_2_error_slots_are_live_and_linked(self):
        response = self.client.get(SIGNUP_URL)
        for name in ("first_name", "last_name", "email", "password1", "password2", "accept_terms"):
            self.assertContains(response, f'aria-describedby="{name}-error"')
            self.assertContains(response, f'id="{name}-error" data-error-for="{name}" class="mt-1 text-xs text-danger" aria-live="polite"')

    def test_AC_2_server_errors_mark_fields_invalid_without_js(self):
        response = self.client.post(SIGNUP_URL, signup_data(first_name="", email="x", accept_terms=None))
        html = response.content.decode()
        for name in ("first_name", "email", "accept_terms"):
            tag = html[html.index(f'name="{name}"') - 300 : html.index(f'name="{name}"') + 300]
            self.assertIn('aria-invalid="true"', tag, name)
        tag = html[html.index('name="last_name"') - 300 : html.index('name="last_name"') + 300]
        self.assertNotIn('aria-invalid="true"', tag)

    def test_AC_3_decomposed_accents_are_accepted_and_stored_composed(self):
        decomposed = unicodedata.normalize("NFD", "José")
        self.assertNotEqual(decomposed, "José")
        self.assertEqual(validate_person_name(decomposed, "x"), "José")
        self.client.post(SIGNUP_URL, signup_data(first_name=decomposed, last_name=unicodedata.normalize("NFD", "Conceição")))
        user = User.objects.get()
        self.assertEqual((user.first_name, user.last_name), ("José", "Conceição"))

    def test_AC_4_database_rejects_same_email_ignoring_case(self):
        User.objects.create_user("um", email="Email@Email.com", password="x")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("dois", email="email@email.com", password="x")
        # Contas sem e-mail continuam permitidas.
        User.objects.create_user("tres", password="x")
        User.objects.create_user("quatro", password="x")

    def test_AC_4_race_on_email_field_shows_friendly_message(self):
        """Conta do admin com o mesmo e-mail criada entre a validação e a gravação."""
        User.objects.create_user("admin", email="maria@exemplo.com", password="x")
        with mock.patch("apps.accounts.forms.email_taken", return_value=False):
            response = self.client.post(SIGNUP_URL, signup_data())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Este e-mail já está cadastrado.")
        self.assertEqual(User.objects.count(), 1)

    def test_AC_5_server_rejects_formats_the_browser_now_rejects(self):
        for email in ("a@b.c", "a..b@x.com", ".a@x.com", "a@x..com"):
            self.assertEqual(SignupForm(signup_data(email=email)).errors.get("email"), ["Informe um e-mail válido."], email)

    def test_AC_5_browser_rules_mirror_server(self):
        from pathlib import Path

        js = (Path(__file__).resolve().parents[3] / "static/js/signup.js").read_text()
        self.assertIn("function emailOk", js)
        self.assertIn('normalize("NFC")', js)

    def test_AC_6_success_message_only_after_real_signup(self):
        response = self.client.post(SIGNUP_URL, signup_data(accept_terms=None), follow=True)
        self.assertNotContains(response, SUCCESS)
        response = self.client.post(SIGNUP_URL, signup_data(), follow=True)
        self.assertContains(response, SUCCESS)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_terms_checkbox_is_not_preselected(self):
        html = self.client.get(SIGNUP_URL).content.decode()
        tag = html[html.index('name="accept_terms"') - 200 : html.index('name="accept_terms"') + 200]
        self.assertNotIn("checked", tag)
