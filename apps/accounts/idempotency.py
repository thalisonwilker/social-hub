"""Chave de idempotência do cadastro: emitida assinada no formulário, válida por 2 horas (spec 0013)."""

import re
import uuid

from django.core import signing

SALT = "accounts.signup.idempotency"
MAX_AGE_SECONDS = 2 * 60 * 60
_KEY_RE = re.compile(r"^[0-9a-f]{32}$")


def issue_key() -> str:
    """Gera uma chave nova, assinada pelo servidor (vai no campo oculto `chave_idempotencia`)."""
    return signing.dumps(uuid.uuid4().hex, salt=SALT)


def read_key(token: str | None) -> str | None:
    """Devolve a chave se a assinatura for válida e tiver até 2 horas; senão, `None`."""
    if not token or len(token) > 200:
        return None
    try:
        key = signing.loads(token, salt=SALT, max_age=MAX_AGE_SECONDS)
    except signing.BadSignature:  # inclui SignatureExpired
        return None
    return key if isinstance(key, str) and _KEY_RE.match(key) else None
