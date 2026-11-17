from django import forms
from django.conf import settings

from .images import ImageValidationError, sanitize_image
from .models import SocialAccount
from .textrules import THREADS_MAX_LINKS, THREADS_MAX_WEIGHT, count_unique_links, threads_weight

FB = SocialAccount.Platform.FACEBOOK_PAGE
THREADS = SocialAccount.Platform.THREADS

MSG_IMAGE_REQUIRED = "Escolha uma imagem (JPEG ou PNG)."


class PublicationForm(forms.Form):
    """Publicação com destinos mistos (Páginas do Facebook e perfis do Threads). Ver ADR-0007.

    - Imagem: obrigatória apenas se houver Página do Facebook marcada; só-Threads → opcional e ignorada.
    - Texto: até 5000; se houver Threads marcado, peso ≤ 500 e no máximo 5 links únicos.
    """

    text = forms.CharField(
        label="Texto",
        strip=True,
        max_length=settings.PUBLICATION_MAX_TEXT_LENGTH,
        widget=forms.Textarea(attrs={"class": "input", "rows": 6, "placeholder": "Escreva o texto da publicação"}),
        error_messages={
            "required": "Escreva o texto da publicação.",
            "max_length": f"O texto pode ter no máximo {settings.PUBLICATION_MAX_TEXT_LENGTH} caracteres.",
        },
    )
    image = forms.FileField(
        label="Imagem",
        required=False,
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png", "class": "input"}),
        error_messages={"invalid": "Envie um arquivo de imagem válido."},
    )
    accounts = forms.ModelMultipleChoiceField(
        label="Destinos",
        queryset=SocialAccount.objects.none(),
        error_messages={
            "required": "Selecione ao menos uma Página ou perfil.",
            "invalid_choice": "Seleção de Página inválida.",
            "invalid_pk_value": "Seleção de Página inválida.",
        },
    )

    def __init__(self, *args, user, platforms=(FB, THREADS), **kwargs):
        super().__init__(*args, **kwargs)
        self.sanitized = None  # imagem sanitizada (None quando não há Página do Facebook)
        self.image_ignored = False  # imagem enviada, mas sem uso (só Threads)
        # Só destinos ATIVOS do próprio usuário, de plataformas configuradas (outro usuário / reauth => escolha inválida).
        self.fields["accounts"].queryset = SocialAccount.objects.filter(
            owner=user, platform__in=list(platforms), status=SocialAccount.Status.ACTIVE
        )

    def clean(self):
        cleaned = super().clean()
        accounts = cleaned.get("accounts")
        if accounts is None:  # erro de seleção já registrado
            return cleaned

        platforms = {account.platform for account in accounts}
        text = cleaned.get("text")
        upload = cleaned.get("image")

        if THREADS in platforms and text:
            weight = threads_weight(text)
            if weight > THREADS_MAX_WEIGHT:
                self.add_error(
                    "text",
                    f"No Threads o texto pode ter até {THREADS_MAX_WEIGHT} (emoji contam mais). O seu tem {weight}.",
                )
            if count_unique_links(text) > THREADS_MAX_LINKS:
                self.add_error("text", f"O Threads aceita no máximo {THREADS_MAX_LINKS} links diferentes.")

        if FB in platforms:
            if not upload:
                self.add_error("image", MSG_IMAGE_REQUIRED)
            else:
                try:
                    self.sanitized = sanitize_image(upload)
                except ImageValidationError as exc:
                    self.add_error("image", str(exc))
        else:
            self.image_ignored = bool(upload)  # só Threads: imagem não é validada, gravada nem enviada
        return cleaned
