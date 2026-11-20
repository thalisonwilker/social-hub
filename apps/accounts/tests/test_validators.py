from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.accounts.validators import (
    PasswordCompositionValidator,
    normalize_email,
    password_composition_errors,
    validate_person_name,
)


class NormalizeEmailTests(SimpleTestCase):
    def test_trims_and_lowercases(self):
        self.assertEqual(normalize_email("  eMaiL@EMAil.com "), "email@email.com")


class PersonNameTests(SimpleTestCase):
    def check_error(self, value, message):
        with self.assertRaisesMessage(ValidationError, message):
            validate_person_name(value, "Informe seu nome.")

    def test_valid_names_are_trimmed(self):
        for value in ("  João ", "Ana-Lúcia", "D'Ávila", "Maria da Silva", "O’Neil", "Zoë"):
            self.assertEqual(validate_person_name(value, "x"), value.strip(), value)

    def test_empty_or_too_short(self):
        for value in ("", "   ", "A", "-'"):
            with self.subTest(value=value):
                # "-'" falha antes por caracteres? Não: hífen e apóstrofo são permitidos; faltam letras.
                self.check_error(value, "Informe seu nome.")

    def test_invalid_characters(self):
        for value in ("Maria1", "<script>", "' OR 1=1 --", "Ana_Paula", "Ana.Paula"):
            with self.subTest(value=value):
                self.check_error(value, "Use apenas letras, espaços, hífen ou apóstrofo.")

    def test_too_long(self):
        self.check_error("a" * 151, "Use no máximo 150 caracteres.")
        self.assertEqual(validate_person_name("a" * 150, "x"), "a" * 150)


class PasswordCompositionTests(SimpleTestCase):
    def test_strong_password_passes(self):
        self.assertEqual(password_composition_errors("Quarto#Azul42"), [])
        PasswordCompositionValidator().validate("Quarto#Azul42")

    def test_one_message_per_missing_rule(self):
        self.assertEqual(
            password_composition_errors("abc"),
            [
                "A senha precisa ter pelo menos 8 caracteres.",
                "A senha precisa de pelo menos uma letra maiúscula.",
                "A senha precisa de pelo menos um número.",
                "A senha precisa de pelo menos um caractere especial (ex.: ! @ # $ %).",
            ],
        )

    def test_space_is_not_special(self):
        self.assertIn(
            "A senha precisa de pelo menos um caractere especial (ex.: ! @ # $ %).",
            password_composition_errors("Quarto Azul42"),
        )
