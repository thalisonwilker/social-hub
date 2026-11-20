from django.apps import AppConfig


class SocialConfig(AppConfig):
    name = "apps.social"
    verbose_name = "Redes sociais"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from .services import profiles

        def reset_profile(sender, request, **kwargs):
            """Cada login começa na escolha de perfil (spec 0011, AC-1)."""
            if request is not None and hasattr(request, "session"):
                profiles.deactivate(request)

        user_logged_in.connect(reset_profile, dispatch_uid="social_reset_active_profile")
