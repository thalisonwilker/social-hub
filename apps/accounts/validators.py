"""Regras de validação do cadastro (spec 0013). Funções puras: sem I/O, sem banco.

As mesmas regras existem no navegador (`static/js/signup.js`); o servidor é quem decide.
"""

import re
import unicodedata

from django.core.exceptions import ValidationError

NAME_MIN_LETTERS = 2
NAME_MAX_LENGTH = 150
PASSWORD_MIN_LENGTH = 8

# Letras (qualquer alfabeto, com acento), espaço, hífen e apóstrofo (reto ou tipográfico).
_NAME_CHARS = re.compile(r"^(?:[^\W\d_]|[ '’-])+$")
_LETTER = re.compile(r"[^\W\d_]")

MSG_NAME_CHARS = "Use apenas letras, espaços, hífen ou apóstrofo."
MSG_NAME_MAX = f"Use no máximo {NAME_MAX_LENGTH} caracteres."


def normalize_email(value: str) -> str:
    """Apara espaços e converte para minúsculas: `eMaiL@EMAil.com` vira `email@email.com`."""
    return (value or "").strip().lower()


def validate_person_name(value: str, empty_message: str) -> str:
    """Valida nome ou sobrenome e devolve o valor aparado.

    `empty_message` é a mensagem para vazio/curto demais ("Informe seu nome." / "Informe seu sobrenome.").
    """
    # NFC: acento decomposto (letra + acento combinante) vira o caractere composto (spec 0015, AC-3).
    cleaned = unicodedata.normalize("NFC", value or "").strip()
    if not cleaned:
        raise ValidationError(empty_message, code="required")
    if len(cleaned) > NAME_MAX_LENGTH:
        raise ValidationError(MSG_NAME_MAX, code="max_length")
    if not _NAME_CHARS.match(cleaned):
        raise ValidationError(MSG_NAME_CHARS, code="invalid")
    if len(_LETTER.findall(cleaned)) < NAME_MIN_LETTERS:
        raise ValidationError(empty_message, code="too_short")
    return cleaned


def password_composition_errors(password: str) -> list[str]:
    """Mensagens (pt-BR) de cada regra de composição não atendida, na ordem da spec."""
    password = password or ""
    errors = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"A senha precisa ter pelo menos {PASSWORD_MIN_LENGTH} caracteres.")
    if not any(ch.isupper() for ch in password):
        errors.append("A senha precisa de pelo menos uma letra maiúscula.")
    if not any(ch.isdigit() for ch in password):
        errors.append("A senha precisa de pelo menos um número.")
    if not any(not ch.isalnum() and not ch.isspace() for ch in password):
        errors.append("A senha precisa de pelo menos um caractere especial (ex.: ! @ # $ %).")
    return errors


class PasswordCompositionValidator:
    """Validador no formato do Django: ≥ 8 caracteres, maiúscula, número e caractere especial."""

    def validate(self, password, user=None):
        errors = password_composition_errors(password)
        if errors:
            raise ValidationError([ValidationError(msg, code="password_composition") for msg in errors])

    def get_help_text(self):
        return (
            f"Pelo menos {PASSWORD_MIN_LENGTH} caracteres, com uma letra maiúscula, "
            "um número e um caractere especial."
        )
