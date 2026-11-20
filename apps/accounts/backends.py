from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


def find_user_by_email(email):
    """Conta pelo e-mail, sem diferenciar maiúsculas: `username` (contas do cadastro) ou, se não houver,
    o campo `email` de uma única conta (contas antigas). Usado pelo login e pela recuperação de senha."""
    if not email or "@" not in email:
        return None
    manager = get_user_model()._default_manager
    email = email.strip()
    by_username = list(manager.filter(username__iexact=email)[:2])
    if len(by_username) == 1:
        return by_username[0]
    if by_username:
        return None
    by_email = list(manager.filter(email__iexact=email)[:2])
    return by_email[0] if len(by_email) == 1 else None


class EmailBackend(ModelBackend):
    """Login só por e-mail, sem diferenciar maiúsculas (spec 0013 AC-8 e spec 0014 AC-4).

    Casa o e-mail com o `username` (contas do cadastro: username = e-mail) e, se não houver, com o
    campo `email` de **uma única** conta (contas antigas, ex.: `admin` com `admin@example.com`).
    Sem "@", ou com o e-mail em mais de uma conta antiga, não autentica. Quando não há conta, o hash
    de senha roda mesmo assim, para o tempo de resposta não revelar se o e-mail existe.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(get_user_model().USERNAME_FIELD)
        if not username or password is None or "@" not in username:
            return None
        user = find_user_by_email(username)
        if user is None:
            get_user_model()().set_password(password)  # iguala o tempo (como o ModelBackend)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
