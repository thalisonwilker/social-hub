"""Test runner do Social Hub: a suíte roda em `PUBLISH_MODE=inline` (spec 0007).

O container de testes usa `config.settings.prod`, cujo padrão é `worker`; sem isto os testes que assumem envio
na requisição quebrariam. Testes do worker usam `override_settings(PUBLISH_MODE="worker")`.
"""
from django.conf import settings
from django.test.runner import DiscoverRunner


class InlinePublishRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        settings.PUBLISH_MODE = "inline"
        settings.ACCOUNTS_EMAIL_ASYNC = False  # e-mails de conta (spec 0016) síncronos no teste
