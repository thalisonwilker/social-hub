"""Rotas das redes sociais: contas conectadas (0002) e publicações (0003).

A agenda ainda é uma página reservada.
"""
from django.urls import path

from apps.core.views import PlaceholderView

from . import views, views_publications

app_name = "social"

urlpatterns = [
    path("contas/facebook/conectar/", views.FacebookConnectView.as_view(), name="facebook_connect"),
    path("contas/facebook/callback/", views.FacebookCallbackView.as_view(), name="facebook_callback"),
    path("contas/facebook/selecionar/", views.FacebookSelectView.as_view(), name="facebook_select"),
    path("contas/", views.AccountsView.as_view(), name="accounts"),
    path("contas/<int:pk>/verificar/", views.AccountCheckView.as_view(), name="account_check"),
    path("contas/<int:pk>/desconectar/", views.AccountDisconnectView.as_view(), name="account_disconnect"),
    path("publicacoes/", views_publications.PostsView.as_view(), name="posts"),
    path("publicacoes/nova/", views_publications.PostNewView.as_view(), name="post_new"),
    path("publicacoes/<int:pk>/", views_publications.PostDetailView.as_view(), name="post_detail"),
    path("publicacoes/<int:pk>/enviar/", views_publications.PostSendView.as_view(), name="post_send"),
    path("publicacoes/<int:pk>/imagem/", views_publications.PostImageView.as_view(), name="post_image"),
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
