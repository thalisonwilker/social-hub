from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("entrar/", views.LoginView.as_view(), name="login"),
    path("sair/", views.LogoutView.as_view(), name="logout"),
    path("cadastro/", views.SignupView.as_view(), name="signup"),
    path("termos/", views.LegalPageView.as_view(template_name="accounts/terms.html"), name="terms"),
    path(
        "privacidade/",
        views.LegalPageView.as_view(template_name="accounts/privacy.html"),
        name="privacy",
    ),
    path("conta/", views.ProfileView.as_view(), name="profile"),
    path("conta/senha/", views.PasswordChangeView.as_view(), name="password_change"),
]
