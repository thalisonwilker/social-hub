"""Rotas das redes sociais.

Por enquanto são páginas reservadas. As integrações (Meta Graph API, Threads),
modelos de contas/publicações e o agendamento serão implementados neste app.
"""
from django.urls import path

from apps.core.views import PlaceholderView

app_name = "social"

urlpatterns = [
    path(
        "contas/",
        PlaceholderView.as_view(
            title="Contas conectadas",
            icon="share-2",
            description="Conecte e gerencie as contas de Facebook, Instagram e Threads.",
            planned=("Autorização OAuth com a Meta", "Status e validade dos tokens", "Múltiplas contas por plataforma"),
        ),
        name="accounts",
    ),
    path(
        "publicacoes/",
        PlaceholderView.as_view(
            title="Publicações",
            icon="file-text",
            description="Crie e publique conteúdos em várias redes ao mesmo tempo.",
            planned=("Editor com pré-visualização por rede", "Biblioteca de mídia", "Histórico e status de publicação"),
        ),
        name="posts",
    ),
    path(
        "agenda/",
        PlaceholderView.as_view(
            title="Agenda",
            icon="calendar-days",
            description="Visualize e agende suas publicações em um calendário.",
            planned=("Calendário mensal e semanal", "Agendamento por data e hora", "Fila de publicações"),
        ),
        name="calendar",
    ),
]
