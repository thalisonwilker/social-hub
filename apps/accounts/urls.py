from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("entrar/", views.LoginView.as_view(), name="login"),
    path("sair/", views.LogoutView.as_view(), name="logout"),
    path("conta/", views.ProfileView.as_view(), name="profile"),
    path("conta/senha/", views.PasswordChangeView.as_view(), name="password_change"),
]
