from django.contrib.auth.decorators import login_not_required
from django.http import JsonResponse
from django.views.generic import TemplateView


@login_not_required
def health(request):
    """Endpoint público usado pelo healthcheck do Docker."""
    return JsonResponse({"status": "ok"})


class PlaceholderView(TemplateView):
    """Página de funcionalidade planejada, ainda não implementada."""

    template_name = "core/placeholder.html"
    title = ""
    icon = "construction"
    description = ""
    planned = ()  # itens previstos para a funcionalidade

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title=self.title,
            icon=self.icon,
            description=self.description,
            planned=self.planned,
        )
        return context
