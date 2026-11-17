from django import forms
from django.conf import settings

from .conf import public_url_configured
from .images import ImageValidationError, sanitize_image
from .models import SocialAccount
from .validators import clean_instance_key, is_valid_instance_name
from .textrules import THREADS_MAX_LINKS, THREADS_MAX_WEIGHT, count_unique_links, threads_weight

FB = SocialAccount.Platform.FACEBOOK_PAGE
THREADS = SocialAccount.Platform.THREADS
WHATSAPP = SocialAccount.Platform.WHATSAPP_STATUS

MSG_IMAGE_REQUIRED = "Escolha uma imagem (JPEG ou PNG)."
MAX_ASPECT_RATIO = 10
MSG_IMAGE_RATIO = "Para o Threads, a imagem não pode ser mais de 10 vezes mais larga que alta (nem o contrário). Escolha outra proporção."
MSG_PUBLIC_URL = (
    "Para enviar imagem ao Threads, o Hub precisa de um endereço público HTTPS. "
    "Configure PUBLIC_BASE_URL (ou use um THREADS_REDIRECT_URI HTTPS) e reinicie."
)


class PublicationForm(forms.Form):
    """Publicação com destinos mistos (Páginas do Facebook, perfis do Threads e Status do WhatsApp). Ver ADR-0007.

    - Imagem: obrigatória apenas se houver Página do Facebook marcada; com Threads marcado ela também vai ao
      Threads (spec 0005): proporção ≤ 10:1 e endereço público HTTPS configurado.
    - Texto: até 5000; se houver Threads marcado, peso ≤ 500 e no máximo 5 links únicos.
    - WhatsApp (spec 0006): imagem opcional (vai em base64, sem endereço público); sem limite de texto além do geral.
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

    def __init__(self, *args, user, platforms=(FB, THREADS, WHATSAPP), **kwargs):
        super().__init__(*args, **kwargs)
        self.sanitized = None  # imagem sanitizada (None quando não há imagem)
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

        if FB in platforms and not upload:
            self.add_error("image", MSG_IMAGE_REQUIRED)
        elif upload:
            try:
                self.sanitized = sanitize_image(upload)
            except ImageValidationError as exc:
                self.add_error("image", str(exc))
            else:
                if THREADS in platforms:
                    if not self.sanitized.aspect_ratio_within(MAX_ASPECT_RATIO):
                        self.add_error("image", MSG_IMAGE_RATIO)
                    elif not public_url_configured():
                        self.add_error("image", MSG_PUBLIC_URL)
        return cleaned


MSG_INSTANCE_NAME = "Nome de instância inválido. Use só letras, números, hífen e sublinhado (até 64 caracteres)."


class WhatsAppInstanceForm(forms.Form):
    """Cadastro de uma instância da Evolution (spec 0006). A chave nunca é reexibida (`render_value=False`)."""

    instance_name = forms.CharField(
        label="Nome da instância",
        strip=True,
        widget=forms.TextInput(attrs={"class": "input", "autocomplete": "off", "spellcheck": "false"}),
        error_messages={"required": MSG_INSTANCE_NAME},
    )
    api_key = forms.CharField(
        label="Chave da instância",
        strip=True,
        widget=forms.PasswordInput(attrs={"class": "input", "autocomplete": "off"}, render_value=False),
        error_messages={"required": "Informe a chave da instância."},
    )
    label = forms.CharField(
        label="Nome de exibição (opcional)",
        required=False,
        strip=True,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "input", "autocomplete": "off"}),
    )

    def clean_instance_name(self):
        name = self.cleaned_data["instance_name"]
        if not is_valid_instance_name(name):
            raise forms.ValidationError(MSG_INSTANCE_NAME)
        return name

    def clean_api_key(self):
        key = clean_instance_key(self.cleaned_data["api_key"])
        if not key:
            raise forms.ValidationError("Informe a chave da instância.")
        return key
