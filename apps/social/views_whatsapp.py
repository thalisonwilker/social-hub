"""Cadastro de instâncias da Evolution (WhatsApp, Status). Ver specs/0006-whatsapp-status.

Sem OAuth: o usuário informa o nome da instância e a chave dela; o host vem só da configuração do servidor.
A chave não é reexibida nem registrada em log.
"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View

from .conf import evolution_configured
from .forms import WhatsAppInstanceForm
from .services import evolution_connect, profiles
from .services.evolution import EvolutionClient
from .validators import is_valid_instance_name


class WhatsAppNewView(View):
    template_name = "social/whatsapp_form.html"

    def _render(self, request, form, status=200):
        context = {"page_title": "Adicionar WhatsApp", "form": form, "configured": evolution_configured()}
        return render(request, self.template_name, context, status=status)

    def get(self, request):
        initial = {}
        instance = request.GET.get("instance", "")
        if is_valid_instance_name(instance):
            initial["instance_name"] = instance
        return self._render(request, WhatsAppInstanceForm(initial=initial))

    def post(self, request):
        if not evolution_configured():
            messages.error(request, evolution_connect.MSG_NOT_CONFIGURED)
            return redirect(profiles.after(request))
        form = WhatsAppInstanceForm(request.POST)
        if not form.is_valid():
            return self._render(request, form)
        data = form.cleaned_data
        try:
            account, _ = evolution_connect.register_instance(
                request.user, data["instance_name"], data["api_key"], data["label"], client=EvolutionClient.from_settings()
            )
        except evolution_connect.RegistrationError as exc:
            form.add_error(None, str(exc))
            return self._render(request, form)
        messages.success(request, f"“{account.name}” foi conectada.")
        profiles.adopt(request, [account])
        return redirect(profiles.after(request, ok=True))
