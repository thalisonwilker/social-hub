"""Índice único no e-mail normalizado dos usuários (spec 0015, AC-4).

`lower(email)` só para e-mails não vazios: contas sem e-mail continuam permitidas. Funciona em
SQLite e PostgreSQL. Se já houver e-mails repetidos (ignorando maiúsculas), a migração para e
não altera ninguém.
"""

from django.db import migrations

INDEX = "accounts_user_email_lower_uniq"


def check_duplicates(apps, schema_editor):
    from django.db.models import Count
    from django.db.models.functions import Lower

    User = apps.get_model("auth", "User")
    repeated = (
        User.objects.exclude(email="")
        .annotate(normalized=Lower("email"))
        .values("normalized")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .count()
    )
    if repeated:
        raise RuntimeError(
            f"{repeated} e-mail(s) aparecem em mais de um usuário (ignorando maiúsculas). "
            "Corrija esses usuários antes de aplicar esta migração."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_loginattempt"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(check_duplicates, migrations.RunPython.noop),
        migrations.RunSQL(
            f"CREATE UNIQUE INDEX {INDEX} ON auth_user (lower(email)) WHERE email <> '';",
            f"DROP INDEX {INDEX};",
        ),
    ]
