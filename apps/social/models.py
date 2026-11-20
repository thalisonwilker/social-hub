from django.conf import settings
from django.db import models
from django.utils import timezone

from .crypto import decrypt_token, encrypt_token


class Profile(models.Model):
    """Perfil (workspace) do usuário: agrupa as Contas conectadas e é escolhido após o login (spec 0011)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profiles")
    name = models.CharField(max_length=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="unique_profile_name_per_owner")]

    def __str__(self) -> str:
        return self.name

    @property
    def initial(self) -> str:
        return (self.name[:1] or "?").upper()

    @property
    def hue(self) -> int:
        """Matiz estável (0–359) para o avatar."""
        return (self.pk or 0) * 47 % 360


class SocialAccount(models.Model):
    """Conta de rede social conectada por um usuário (hoje: Página do Facebook)."""

    class Platform(models.TextChoices):
        FACEBOOK_PAGE = "facebook_page", "Página do Facebook"
        THREADS = "threads", "Perfil do Threads"
        WHATSAPP_STATUS = "whatsapp_status", "WhatsApp (Status)"
        INSTAGRAM = "instagram", "Instagram"

    class Status(models.TextChoices):
        ACTIVE = "active", "Ativa"
        NEEDS_REAUTH = "needs_reauth", "Reconexão necessária"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_accounts"
    )
    profile = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.CASCADE, related_name="accounts")
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
    # Conta Instagram (spec 0009): a Página do Facebook pela qual ela é alcançada; remover a Página remove a conta.
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="linked_accounts"
    )

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
        UNCERTAIN = "uncertain", "Incerta"

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
        if counts["uncertain"]:  # resultado desconhecido: só o usuário resolve (spec 0007)
            return self.Status.UNCERTAIN
        if total and counts["published"] == total:
            return self.Status.PUBLISHED
        return self.Status.PENDING

    @property
    def status_label(self) -> str:
        return self.Status(self.status).label

    @property
    def has_retryable_targets(self) -> bool:
        return any(t.is_retryable for t in self.targets.all())

    @property
    def has_resolvable_targets(self) -> bool:
        return any(t.is_resolvable for t in self.targets.all())


class PublicationTarget(models.Model):
    """Par (Publicação, Página): estado e resultado do envio àquela Página."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        SENDING = "sending", "Enviando"
        PUBLISHED = "published", "Publicado"
        FAILED = "failed", "Falhou"
        # O Hub não sabe se a plataforma publicou (spec 0007): nunca é reenviado sozinho; o usuário resolve.
        UNCERTAIN = "uncertain", "Incerto"

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
    # Spec 0010: o post foi apagado NA PLATAFORMA (o alvo continua `published`; o registro fica no histórico).
    deleted_at = models.DateTimeField(null=True, blank=True)

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
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_retryable(self) -> bool:
        """Pendente ou falho, e com a conta ainda conectada. `published` nunca é reenviado."""
        return self.status in (self.Status.PENDING, self.Status.FAILED) and self.account_id is not None

    @property
    def can_try_again(self) -> bool:
        """"Tentar novamente" (modo worker): só alvo `failed` com a conta ainda conectada."""
        return self.status == self.Status.FAILED and self.account_id is not None

    @property
    def is_resolvable(self) -> bool:
        """Alvo Incerto: o usuário decide "Já foi publicado" ou "Reenviar" (funciona mesmo sem conta)."""
        return self.status == self.Status.UNCERTAIN

    @property
    def can_resend(self) -> bool:
        """"Reenviar" um alvo Incerto exige a conta conectada."""
        return self.is_resolvable and self.account_id is not None


class WorkerHeartbeat(models.Model):
    """Batida do worker de envio (spec 0007): uma linha só; diz se há worker ativo. Sem segredos nem conteúdo."""

    DEFAULT_NAME = "default"

    name = models.CharField(max_length=32, unique=True, default=DEFAULT_NAME)
    started_at = models.DateTimeField(default=timezone.now)
    beat_at = models.DateTimeField(default=timezone.now)
    pid = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"Worker {self.name} (pid {self.pid})"

    @classmethod
    def start(cls, *, pid: int) -> "WorkerHeartbeat":
        """Nova partida do worker: renova `started_at`, `beat_at` e o pid."""
        now = timezone.now()
        beat, _ = cls.objects.update_or_create(
            name=cls.DEFAULT_NAME, defaults={"started_at": now, "beat_at": now, "pid": pid}
        )
        return beat

    @classmethod
    def beat(cls, *, pid: int) -> "WorkerHeartbeat":
        """Bate o coração: atualiza `beat_at` (cria a linha se não existir)."""
        now = timezone.now()
        updated = cls.objects.filter(name=cls.DEFAULT_NAME).update(beat_at=now, pid=pid)
        if not updated:
            return cls.objects.create(name=cls.DEFAULT_NAME, started_at=now, beat_at=now, pid=pid)
        return cls.objects.get(name=cls.DEFAULT_NAME)

    @classmethod
    def is_active(cls, now=None) -> bool:
        """Ativo ⇔ a última batida é mais recente que WORKER_HEARTBEAT_STALE_SECONDS. Sem linha = inativo."""
        from datetime import timedelta

        beat_at = cls.objects.filter(name=cls.DEFAULT_NAME).values_list("beat_at", flat=True).first()
        if beat_at is None:
            return False
        return ((now or timezone.now()) - beat_at) <= timedelta(seconds=settings.WORKER_HEARTBEAT_STALE_SECONDS)



class AiProviderKey(models.Model):
    """Chave de API de um provedor de IA (hoje só Gemini), do próprio usuário, SEMPRE cifrada (spec 0008, ADR-0012)."""

    GEMINI = "gemini"
    DEEPSEEK = "deepseek"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_keys")
    provider = models.CharField(max_length=16, default=GEMINI)
    api_key_enc = models.TextField(editable=False)
    last4 = models.CharField(max_length=4, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "provider"], name="unique_ai_key_per_owner")]

    def __str__(self) -> str:  # nunca inclui a chave
        return f"Chave {self.provider} de {self.owner_id}"

    def set_key(self, key: str) -> None:
        self.api_key_enc = encrypt_token(key)
        self.last4 = key[-4:]

    def get_key(self) -> str:
        return decrypt_token(self.api_key_enc)


class GeneratedImage(models.Model):
    """Imagem gerada por IA, já sanitizada, temporária (expira); vira a imagem da publicação ao publicar (spec 0008)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="generated_images")
    file = models.FileField(upload_to="generated/%Y/%m/")
    content_type = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self, now=None) -> bool:
        ttl = settings.GENERATED_IMAGE_TTL_SECONDS
        return (now or timezone.now()).timestamp() - self.created_at.timestamp() > ttl

    @classmethod
    def purge_expired(cls) -> None:
        """Limpeza oportunista (arquivo e linha) das imagens vencidas."""
        cutoff = timezone.now() - timezone.timedelta(seconds=settings.GENERATED_IMAGE_TTL_SECONDS)
        for item in cls.objects.filter(created_at__lt=cutoff):
            item.file.delete(save=False)
            item.delete()
