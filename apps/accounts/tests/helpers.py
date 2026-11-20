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


LOGIN_URL = reverse("accounts:login")


def login_data(email, password, key=None, **extra):
    """POST do login (spec 0014) com uma chave de idempotência nova, salvo se `key` for dada."""
    import uuid

    data = {"email": email, "password": password, "chave_idempotencia": key or str(uuid.uuid4())}
    data.update(extra)
    return data
