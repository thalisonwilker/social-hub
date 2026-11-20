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
