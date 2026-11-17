from django import forms
from django.conf import settings

from .images import ImageValidationError, sanitize_image
from .models import SocialAccount


class PublicationForm(forms.Form):
    text = forms.CharField(
        label="Texto",
        strip=True,
        max_length=settings.PUBLICATION_MAX_TEXT_LENGTH,
        widget=forms.Textarea(attrs={"class": "input", "rows": 6, "placeholder": "Escreva a legenda da publicação"}),
        error_messages={
            "required": "Escreva o texto da publicação.",
            "max_length": f"O texto pode ter no máximo {settings.PUBLICATION_MAX_TEXT_LENGTH} caracteres.",
        },
    )
    image = forms.FileField(
        label="Imagem",
        widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png", "class": "input"}),
        error_messages={"required": "Escolha uma imagem (JPEG ou PNG).", "invalid": "Envie um arquivo de imagem válido."},
    )
    accounts = forms.ModelMultipleChoiceField(
        label="Páginas",
        queryset=SocialAccount.objects.none(),
        error_messages={
            "required": "Selecione ao menos uma Página.",
            "invalid_choice": "Seleção de Página inválida.",
            "invalid_pk_value": "Seleção de Página inválida.",
        },
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.sanitized = None
        # Só Páginas ATIVAS do próprio usuário podem ser alvo (outro usuário / reauth => escolha inválida).
        self.fields["accounts"].queryset = SocialAccount.objects.filter(
            owner=user, platform=SocialAccount.Platform.FACEBOOK_PAGE, status=SocialAccount.Status.ACTIVE
        )

    def clean_image(self):
        upload = self.cleaned_data["image"]
        try:
            self.sanitized = sanitize_image(upload)
        except ImageValidationError as exc:
            raise forms.ValidationError(str(exc)) from None
        return upload
