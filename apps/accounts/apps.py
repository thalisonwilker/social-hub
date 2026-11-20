from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    verbose_name = "Contas de usuário"

    def ready(self):
        from . import checks  # noqa: F401 — registra o system check do e-mail (spec 0016)
