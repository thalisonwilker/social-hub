"""Regras da recuperação de senha (spec 0016, ADR-0017): token, limites, consumo e encerramento de sessões."""

import hashlib
import math
import secrets
from datetime import timedelta

from django.contrib.sessions.models import Session
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import PasswordResetRequest, PasswordResetToken

TOKEN_TTL = timedelta(minutes=30)
IP_WINDOW = timedelta(minutes=15)
MAX_REQUESTS_PER_IP = 5
ACCOUNT_WINDOW = timedelta(hours=1)
MAX_EMAILS_PER_ACCOUNT = 1
RETENTION = timedelta(hours=24)
SESSION_KEY = "accounts.password_reset_token"


def hash_token(token: str) -> str:
    """SHA-256 do token (256 bits aleatórios): o banco nunca guarda o valor original."""
    return hashlib.sha256(token.encode()).hexdigest()


def password_fingerprint(user) -> str:
    """Muda sempre que a senha muda: tokens emitidos antes de qualquer troca deixam de valer."""
    return salted_hmac("accounts.password_reset.fingerprint", user.password, algorithm="sha256").hexdigest()


def ip_retry_after(ip, now=None):
    """Segundos até liberar, se o IP já fez o máximo de pedidos na janela; senão, `None`."""
    if not ip:
        return None
    now = now or timezone.now()
    times = list(
        PasswordResetRequest.objects.filter(ip=ip, created_at__gte=now - IP_WINDOW)
        .order_by("-created_at")
        .values_list("created_at", flat=True)[:MAX_REQUESTS_PER_IP]
    )
    if len(times) < MAX_REQUESTS_PER_IP:
        return None
    return max(1, math.ceil((times[-1] + IP_WINDOW - now).total_seconds()))


def account_limited(user, now=None) -> bool:
    """A conta já recebeu o máximo de e-mails de recuperação na última hora."""
    now = now or timezone.now()
    recent = PasswordResetToken.objects.filter(user=user, created_at__gte=now - ACCOUNT_WINDOW).count()
    return recent >= MAX_EMAILS_PER_ACCOUNT


def issue_token(user, now=None) -> str:
    """Invalida os links pendentes da conta e cria um novo; devolve o token em claro (só para o e-mail)."""
    now = now or timezone.now()
    invalidate_all(user, now)
    token = secrets.token_urlsafe(32)
    PasswordResetToken.objects.create(
        user=user,
        token_hash=hash_token(token),
        password_fingerprint=password_fingerprint(user),
        expires_at=now + TOKEN_TTL,
    )
    return token


def _valid(queryset, now):
    return queryset.filter(used_at__isnull=True, invalidated_at__isnull=True, expires_at__gt=now)


def _usable(reset_token):
    user = reset_token.user
    return user.is_active and reset_token.password_fingerprint == password_fingerprint(user)


def find_valid_token(raw_token, now=None):
    """Token válido pelo valor do link (consulta pelo hash); senão, `None`."""
    if not raw_token or len(raw_token) > 128:
        return None
    now = now or timezone.now()
    found = _valid(PasswordResetToken.objects, now).filter(token_hash=hash_token(raw_token)).select_related("user").first()
    return found if found and _usable(found) else None


def get_valid_token(token_id, now=None):
    """Token válido pela referência guardada na sessão; senão, `None`."""
    if not isinstance(token_id, int):
        return None
    now = now or timezone.now()
    found = _valid(PasswordResetToken.objects, now).filter(pk=token_id).select_related("user").first()
    return found if found and _usable(found) else None


def consume(reset_token, now=None) -> bool:
    """Marca o token como usado só se ainda for válido: em envios simultâneos, um único vence."""
    now = now or timezone.now()
    return _valid(PasswordResetToken.objects, now).filter(pk=reset_token.pk).update(used_at=now) == 1


def invalidate_all(user, now=None):
    now = now or timezone.now()
    PasswordResetToken.objects.filter(user=user, used_at__isnull=True, invalidated_at__isnull=True).update(
        invalidated_at=now
    )


def revoke_sessions(user):
    """Apaga todas as sessões (no banco) em que a conta está autenticada."""
    user_id = str(user.pk)
    doomed = [
        s.session_key
        for s in Session.objects.filter(expire_date__gte=timezone.now()).iterator()
        if s.get_decoded().get("_auth_user_id") == user_id
    ]
    Session.objects.filter(session_key__in=doomed).delete()


def purge_old(now=None):
    """Retenção de 24 h para pedidos e tokens vencidos (chamado a cada pedido)."""
    now = now or timezone.now()
    PasswordResetRequest.objects.filter(created_at__lt=now - RETENTION).delete()
    PasswordResetToken.objects.filter(expires_at__lt=now - RETENTION).delete()
