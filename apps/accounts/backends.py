from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    """Login por e-mail sem diferenciar maiúsculas (spec 0013, AC-8).

    No cadastro, `username` = e-mail em minúsculas; aqui a entrada com "@" casa o `username` sem
    diferenciar maiúsculas. Sem "@" (usuários antigos, ex.: `admin`), vale o comportamento padrão.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username and "@" in username and password is not None:
            matches = list(get_user_model()._default_manager.filter(username__iexact=username.strip())[:2])
            if len(matches) == 1:
                user = matches[0]
                if user.check_password(password) and self.user_can_authenticate(user):
                    return user
                return None
        return super().authenticate(request, username=username, password=password, **kwargs)
