"""Rotas das redes sociais.

Por enquanto são páginas reservadas. As integrações (Meta Graph API, Threads),
modelos de contas/publicações e o agendamento serão implementados neste app.
"""
from django.urls import path

from apps.core.views import PlaceholderView

from . import views

app_name = "social"

urlpatterns = [
    path("contas/facebook/conectar/", views.FacebookConnectView.as_view(), name="facebook_connect"),
    path("contas/facebook/callback/", views.FacebookCallbackView.as_view(), name="facebook_callback"),
    path("contas/facebook/selecionar/", views.FacebookSelectView.as_view(), name="facebook_select"),
    path("contas/", views.AccountsView.as_view(), name="accounts"),
    path("contas/<int:pk>/verificar/", views.AccountCheckView.as_view(), name="account_check"),
    path("contas/<int:pk>/desconectar/", views.AccountDisconnectView.as_view(), name="account_disconnect"),
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
