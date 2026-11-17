from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

INPUT_CLASS = "input"


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Usuário"
        self.fields["username"].widget.attrs.update(
            {"class": INPUT_CLASS, "autofocus": True, "autocomplete": "username"}
        )
        self.fields["password"].widget.attrs.update(
            {"class": INPUT_CLASS, "autocomplete": "current-password"}
        )


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = INPUT_CLASS
            field.widget.attrs["autocomplete"] = (
                "current-password" if name == "old_password" else "new-password"
            )
