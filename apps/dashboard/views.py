from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.social.models import SocialAccount
from apps.social.services import profiles, threads_tokens

from . import demo

PLATFORM_NAMES = {
    SocialAccount.Platform.FACEBOOK_PAGE: "Facebook",
    SocialAccount.Platform.THREADS: "Threads",
}


class DashboardView(TemplateView):
    template_name = "dashboard/index.html"

    def dispatch(self, request, *args, **kwargs):
        # Quem tem Perfis precisa escolher um antes do painel (spec 0011, AC-9).
        if request.user.is_authenticated and not profiles.get_active(request) and request.user.profiles.exists():
            return redirect("social:profile_select")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        threads_tokens.expire_stale_tokens(self.request.user)
        active = profiles.scope(
            self.request,
            SocialAccount.objects.filter(owner=self.request.user, status=SocialAccount.Status.ACTIVE),
        ).values_list("platform", flat=True)
        connected = {PLATFORM_NAMES[p] for p in active if p in PLATFORM_NAMES}
        context.update(
            page_title="Visão geral",
            kpis=demo.kpis(),
            weekly_reach=demo.weekly_reach(),
            platforms=demo.platforms(connected),
            recent_posts=demo.recent_posts(),
        )
        return context
