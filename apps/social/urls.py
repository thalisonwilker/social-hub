"""Rotas das redes sociais: contas conectadas (0002) e publicações (0003).

A agenda ainda é uma página reservada.
"""
from django.urls import path, re_path

from apps.core.views import PlaceholderView

from . import views, views_ai, views_profiles, views_public, views_publications, views_threads, views_whatsapp

app_name = "social"

urlpatterns = [
    path("perfis/", views_profiles.ProfileSelectView.as_view(), name="profile_select"),
    path("perfis/novo/", views_profiles.ProfileNewView.as_view(), name="profile_new"),
    path("perfis/<int:pk>/entrar/", views_profiles.ProfileEnterView.as_view(), name="profile_enter"),
    path("perfis/<int:pk>/conectar/", views_profiles.ProfileConnectView.as_view(), name="profile_connect"),
    path("perfis/<int:pk>/concluir/", views_profiles.ProfileDoneView.as_view(), name="profile_done"),
    path("contas/facebook/conectar/", views.FacebookConnectView.as_view(), name="facebook_connect"),
    path("contas/facebook/callback/", views.FacebookCallbackView.as_view(), name="facebook_callback"),
    path("contas/facebook/selecionar/", views.FacebookSelectView.as_view(), name="facebook_select"),
    path("contas/threads/conectar/", views_threads.ThreadsConnectView.as_view(), name="threads_connect"),
    path("contas/threads/callback/", views_threads.ThreadsCallbackView.as_view(), name="threads_callback"),
    path("contas/whatsapp/nova/", views_whatsapp.WhatsAppNewView.as_view(), name="whatsapp_new"),
    path("contas/", views.AccountsView.as_view(), name="accounts"),
    path("contas/<int:pk>/verificar/", views.AccountCheckView.as_view(), name="account_check"),
    path("contas/<int:pk>/desconectar/", views.AccountDisconnectView.as_view(), name="account_disconnect"),
    path("publicacoes/", views_publications.PostsView.as_view(), name="posts"),
    path("publicacoes/nova/", views_publications.PostNewView.as_view(), name="post_new"),
    path("publicacoes/<int:pk>/", views_publications.PostDetailView.as_view(), name="post_detail"),
    path("publicacoes/<int:pk>/enviar/", views_publications.PostSendView.as_view(), name="post_send"),
    path("publicacoes/<int:pk>/estado/", views_publications.PostStateView.as_view(), name="post_state"),
    path(
        "publicacoes/<int:pk>/alvos/<int:target_pk>/resolver/",
        views_publications.TargetResolveView.as_view(),
        name="target_resolve",
    ),
    path("publicacoes/<int:pk>/remover/", views_publications.PostRemoveView.as_view(), name="post_remove"),
    path("publicacoes/<int:pk>/apagar/", views_publications.PostDeleteRemoteView.as_view(), name="post_delete_remote"),
    path(
        "publicacoes/<int:pk>/alvos/<int:target_pk>/remover/",
        views_publications.TargetRemoveView.as_view(),
        name="target_remove",
    ),
    path(
        "publicacoes/<int:pk>/alvos/<int:target_pk>/apagar/",
        views_publications.TargetDeleteRemoteView.as_view(),
        name="target_delete_remote",
    ),
    path("publicacoes/<int:pk>/imagem/", views_publications.PostImageView.as_view(), name="post_image"),
    path("publicacoes/imagem-ia/gerar/", views_ai.GenerateImageView.as_view(), name="ai_generate"),
    path("publicacoes/imagem-ia/chave/", views_ai.SaveKeyView.as_view(), name="ai_key_save"),
    path("publicacoes/texto-ia/gerar/", views_ai.GenerateTextView.as_view(), name="ai_text"),
    path("publicacoes/imagem-ia/chave/testar/", views_ai.TestKeyView.as_view(), name="ai_key_test"),
    path("publicacoes/imagem-ia/chave/remover/", views_ai.RemoveKeyView.as_view(), name="ai_key_remove"),
    path("publicacoes/imagem-ia/<int:pk>/", views_ai.GeneratedImageView.as_view(), name="ai_image"),
    re_path(r"^publico/imagem\.(?P<ext>jpg|png)$", views_public.PublicImageView.as_view(), name="public_image"),
    path("publico/instagram.jpg", views_public.PublicInstagramImageView.as_view(), name="public_instagram_image"),
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
