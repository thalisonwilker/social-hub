"""Limitação de tentativas de login e idempotência por tentativa (spec 0014, ADR-0016)."""

import math
import uuid
from datetime import timedelta

from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import LoginAttempt

WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_EMAIL = 5
MAX_FAILURES_PER_IP = 20
RETENTION = timedelta(hours=24)


def hash_email(email: str) -> str:
    """HMAC-SHA256 do e-mail normalizado com a SECRET_KEY: o e-mail nunca é guardado em claro."""
    return salted_hmac("accounts.login.email", email, algorithm="sha256").hexdigest()


def parse_key(value: str | None) -> uuid.UUID | None:
    """Aceita só UUID no formato canônico (36 caracteres); senão, `None`."""
    if not value or len(value) != 36:
        return None
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return None
    return parsed if str(parsed) == value.lower() else None


def client_ip(request) -> str | None:
    """IP do `REMOTE_ADDR` (não confia em X-Forwarded-For; ver ADR-0016)."""
    return request.META.get("REMOTE_ADDR") or None


def retry_after(email_hash: str, ip: str | None, now=None) -> int | None:
    """Segundos até liberar, se o e-mail ou o IP estiver bloqueado; senão, `None`."""
    now = now or timezone.now()
    since = now - WINDOW
    waits = []

    last_success = (
        LoginAttempt.objects.filter(email_hash=email_hash, succeeded=True, created_at__gte=since)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    email_failures = LoginAttempt.objects.filter(
        email_hash=email_hash, succeeded=False, created_at__gte=last_success or since
    )
    waits.append(_wait(email_failures, MAX_FAILURES_PER_EMAIL, now))
    if ip:
        ip_failures = LoginAttempt.objects.filter(ip=ip, succeeded=False, created_at__gte=since)
        waits.append(_wait(ip_failures, MAX_FAILURES_PER_IP, now))

    waits = [w for w in waits if w is not None]
    return max(waits) if waits else None


def _wait(failures, limit, now):
    """Se há `limit` falhas ou mais, espera até a falha que precisa sair da janela sair dela."""
    times = list(failures.order_by("-created_at").values_list("created_at", flat=True)[:limit])
    if len(times) < limit:
        return None
    # Liberado quando sobrarem `limit - 1` falhas: a `limit`-ésima mais recente sai da janela.
    seconds = (times[-1] + WINDOW - now).total_seconds()
    return max(1, math.ceil(seconds))


def purge_old(now=None):
    """Apaga tentativas com mais de 24 h (chamado a cada POST de login)."""
    LoginAttempt.objects.filter(created_at__lt=(now or timezone.now()) - RETENTION).delete()
