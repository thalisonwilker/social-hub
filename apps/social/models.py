from django.conf import settings
from django.db import models
from django.utils import timezone

from .crypto import decrypt_token, encrypt_token


class SocialAccount(models.Model):
    """Conta de rede social conectada por um usuário (hoje: Página do Facebook)."""

    class Platform(models.TextChoices):
        FACEBOOK_PAGE = "facebook_page", "Página do Facebook"
        THREADS = "threads", "Perfil do Threads"

    class Status(models.TextChoices):
        ACTIVE = "active", "Ativa"
        NEEDS_REAUTH = "needs_reauth", "Reconexão necessária"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_accounts"
    )
    platform = models.CharField(max_length=32, choices=Platform.choices)
    external_id = models.CharField("ID na plataforma", max_length=64)
    name = models.CharField(max_length=255)
    username = models.CharField(max_length=64, blank=True)  # @usuário (Threads)
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
    # Só para tokens que expiram (Threads, 60 dias). Páginas do Facebook não expiram: ficam nulos.
    token_expires_at = models.DateTimeField(null=True, blank=True)
    token_refreshed_at = models.DateTimeField(null=True, blank=True)

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

    def token_expired(self, now=None) -> bool:
        """True se o token tem validade e ela já passou (Páginas do Facebook nunca expiram)."""
        return self.token_expires_at is not None and self.token_expires_at <= (now or timezone.now())

    def days_until_token_expiry(self, now=None) -> int | None:
        """Dias inteiros até a expiração (0 se já passou); None se o token não expira."""
        if self.token_expires_at is None:
            return None
        delta = self.token_expires_at - (now or timezone.now())
        return max(0, delta.days)


class Publication(models.Model):
    """Conteúdo (texto + 1 imagem) a ser publicado em uma ou mais Páginas."""

    class Status(models.TextChoices):  # status GERAL, sempre derivado dos alvos
        PENDING = "pending", "Pendente"
        PUBLISHED = "published", "Publicada"
        FAILED = "failed", "Com falhas"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="publications"
    )
    text = models.TextField()
    # Opcional: publicações só do Threads não têm imagem (obrigatória só com Página do Facebook).
    image = models.FileField(upload_to="publications/%Y/%m/", blank=True)
    image_content_type = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:  # nunca inclui o texto completo
        return f"Publicação #{self.pk}"

    @property
    def has_image(self) -> bool:
        return bool(self.image)

    def status_counts(self) -> dict:
        counts = {s.value: 0 for s in PublicationTarget.Status}
        for target in self.targets.all():
            counts[target.status] += 1
        return counts

    @property
    def status(self) -> str:
        counts = self.status_counts()
        total = sum(counts.values())
        if counts["failed"]:
            return self.Status.FAILED
        if total and counts["published"] == total:
            return self.Status.PUBLISHED
        return self.Status.PENDING

    @property
    def status_label(self) -> str:
        return self.Status(self.status).label

    @property
    def has_retryable_targets(self) -> bool:
        return any(t.is_retryable for t in self.targets.all())


class PublicationTarget(models.Model):
    """Par (Publicação, Página): estado e resultado do envio àquela Página."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        SENDING = "sending", "Enviando"
        PUBLISHED = "published", "Publicado"
        FAILED = "failed", "Falhou"

    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name="targets")
    account = models.ForeignKey(
        SocialAccount, null=True, blank=True, on_delete=models.SET_NULL, related_name="publication_targets"
    )
    # Snapshot: o histórico sobrevive à desconexão da conta.
    page_external_id = models.CharField(max_length=64)
    page_name = models.CharField(max_length=255)
    platform = models.CharField(
        max_length=32, choices=SocialAccount.Platform.choices, default=SocialAccount.Platform.FACEBOOK_PAGE
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    external_post_id = models.CharField(max_length=128, blank=True)
    # Threads: id do container, gravado ANTES de publicar para retomar sem recriar (ADR-0007).
    external_container_id = models.CharField(max_length=128, blank=True)
    permalink = models.URLField(max_length=500, blank=True)
    error_message = models.CharField(max_length=255, blank=True)  # SEMPRE amigável
    error_code = models.CharField(max_length=32, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["page_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "page_external_id"], name="unique_target_per_page"
            )
        ]

    def __str__(self) -> str:
        return f"{self.page_name} · {self.get_status_display()}"

    @property
    def is_retryable(self) -> bool:
        """Pendente ou falho, e com a conta ainda conectada. `published` nunca é reenviado."""
        return self.status in (self.Status.PENDING, self.Status.FAILED) and self.account_id is not None
