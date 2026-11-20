from django.urls import reverse

from apps.accounts import idempotency

SIGNUP_URL = reverse("accounts:signup")
STRONG_PASSWORD = "Quarto#Azul42"


def signup_data(**overrides):
    data = {
        "first_name": "Maria",
        "last_name": "da Silva",
        "email": "maria@exemplo.com",
        "password1": STRONG_PASSWORD,
        "password2": STRONG_PASSWORD,
        "accept_terms": "on",
        "chave_idempotencia": idempotency.issue_key(),
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}
