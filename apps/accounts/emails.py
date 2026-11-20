"""E-mails de conta (spec 0016, ADR-0017): texto simples em pt-BR, enviados fora da requisição.

O conteúdo (que pode ter o link com token) nunca vai para o log; falhas registram só o tipo do e-mail.
"""

import logging
import threading

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger("apps.accounts.emails")


def recipient_for(user):
    """E-mail da conta: o campo `email` ou, nas contas do cadastro, o `username` (= e-mail)."""
    if user.email:
        return user.email
    return user.username if "@" in user.username else None


def _deliver(kind, subject, body, to):
    try:
        send_mail(subject, body, None, [to], fail_silently=False)
    except Exception as error:  # noqa: BLE001 — qualquer falha de SMTP vira log sem conteúdo
        logger.warning("email %s falhou (%s)", kind, type(error).__name__)


def _send(kind, subject, body, to):
    if not to:
        return
    if settings.ACCOUNTS_EMAIL_ASYNC:
        threading.Thread(target=_deliver, args=(kind, subject, body, to), daemon=True).start()
    else:
        _deliver(kind, subject, body, to)


def reset_link(request, token):
    base = (settings.PUBLIC_BASE_URL or request.build_absolute_uri("/")).rstrip("/")
    return f"{base}{reverse('accounts:password_reset_confirm')}?token={token}"


def send_reset_link(request, user, token):
    body = (
        "Olá,\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta no Social Hub.\n"
        "Para escolher uma nova senha, abra o link abaixo:\n\n"
        f"{reset_link(request, token)}\n\n"
        "O link vale por 30 minutos e pode ser usado uma única vez.\n"
        "Se não foi você, ignore este e-mail: sua senha continua a mesma.\n"
    )
    _send("link", "Redefinição de senha do Social Hub", body, recipient_for(user))


def send_password_changed(user):
    when = timezone.localtime().strftime("%d/%m/%Y às %H:%M")
    body = (
        "Olá,\n\n"
        f"A senha da sua conta no Social Hub foi alterada em {when}.\n\n"
        "Se foi você, nada mais precisa ser feito.\n"
        "Se não foi você, peça uma nova recuperação de senha na tela de login imediatamente.\n"
    )
    _send("aviso", "Sua senha do Social Hub foi alterada", body, recipient_for(user))
