from django.views.generic import TemplateView

from . import demo


class DashboardView(TemplateView):
    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title="Visão geral",
            kpis=demo.kpis(),
            weekly_reach=demo.weekly_reach(),
            platforms=demo.platforms(),
            recent_posts=demo.recent_posts(),
        )
        return context
