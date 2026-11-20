from django.conf import settings
from django.db import models


class SignupIdempotencyKey(models.Model):
    """Chave de idempotência do cadastro (spec 0013, AC-11).

    Gravada na mesma transação que cria o usuário; a unicidade de `key` garante que requisições
    repetidas com a mesma chave criem no máximo um usuário (a trava fica no banco porque há mais de
    um worker do gunicorn e nenhum cache compartilhado).
    """

    key = models.CharField(max_length=32, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="signup_keys"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "chave de idempotência do cadastro"
        verbose_name_plural = "chaves de idempotência do cadastro"

    def __str__(self):
        return self.key


class LoginAttempt(models.Model):
    """Tentativa de login com credenciais (spec 0014, ADR-0016).

    Serve à limitação de tentativas (falhas por e-mail e por IP numa janela) e à idempotência
    (a chave é única; repetições leem o resultado). Não guarda senha, e-mail em claro nem sessão.
    """

    key = models.UUIDField(unique=True)
    email_hash = models.CharField(max_length=64, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    succeeded = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "tentativa de login"
        verbose_name_plural = "tentativas de login"

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {'ok' if self.succeeded else 'falha'}"
