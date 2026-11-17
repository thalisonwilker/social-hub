from django.conf import settings
from django.db import models

from .crypto import decrypt_token, encrypt_token


class SocialAccount(models.Model):
    """Conta de rede social conectada por um usuário (hoje: Página do Facebook)."""

    class Platform(models.TextChoices):
        FACEBOOK_PAGE = "facebook_page", "Página do Facebook"

    class Status(models.TextChoices):
        ACTIVE = "active", "Ativa"
        NEEDS_REAUTH = "needs_reauth", "Reconexão necessária"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_accounts"
    )
    platform = models.CharField(max_length=32, choices=Platform.choices)
    external_id = models.CharField("ID na plataforma", max_length=64)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255, blank=True)
    picture_url = models.URLField(max_length=500, blank=True)
    # Token SEMPRE criptografado (ADR-0002). Use set_token()/get_token().
    access_token_enc = models.TextField(editable=False)
    granted_tasks = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    last_error = models.CharField(max_length=255, blank=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "platform", "external_id"], name="unique_account_per_owner"
            )
        ]

    def __str__(self) -> str:  # nunca inclui o token
        return f"{self.name} ({self.get_platform_display()})"

    def set_token(self, token: str) -> None:
        self.access_token_enc = encrypt_token(token)

    def get_token(self) -> str:
        return decrypt_token(self.access_token_enc)

    @property
    def needs_reauth(self) -> bool:
        return self.status == self.Status.NEEDS_REAUTH
