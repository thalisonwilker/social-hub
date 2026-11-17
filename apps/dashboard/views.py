from django.views.generic import TemplateView

from apps.social.models import SocialAccount
from apps.social.services import threads_tokens

from . import demo

PLATFORM_NAMES = {
    SocialAccount.Platform.FACEBOOK_PAGE: "Facebook",
    SocialAccount.Platform.THREADS: "Threads",
}


class DashboardView(TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        threads_tokens.expire_stale_tokens(self.request.user)
        active = SocialAccount.objects.filter(
            owner=self.request.user, status=SocialAccount.Status.ACTIVE
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
