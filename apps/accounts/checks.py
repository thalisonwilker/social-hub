from django.conf import settings
from django.core.checks import Warning, register


@register()
def email_configured(app_configs, **kwargs):
    """Produção sem SMTP: os e-mails de conta (spec 0016) ficariam só em arquivo no servidor."""
    if settings.DEBUG or settings.EMAIL_HOST:
        return []
    return [
        Warning(
            "EMAIL_HOST não configurado: os e-mails de recuperação de senha vão para arquivos em var/emails/.",
            hint="Defina EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD e DEFAULT_FROM_EMAIL no .env.",
            id="accounts.W001",
        )
    ]
