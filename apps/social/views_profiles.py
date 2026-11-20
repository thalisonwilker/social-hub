"""Perfis: seleção pós-login e wizard de criação/conexão. Ver specs/0011-perfis-e-wizard."""
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .conf import evolution_configured, meta_configured, threads_configured
from .forms import ProfileForm
from .models import Profile, SocialAccount
from .services import profiles

STEPS = ("Nome", "Conectar", "Pronto")


class ProfileSelectView(View):
    """"Quem está usando?": os perfis do usuário e o cartão +."""

    def get(self, request):
        profiles.deactivate(request)
        items = list(request.user.profiles.all())
        counts = {}
        for pid in SocialAccount.objects.filter(owner=request.user, profile__in=items).values_list("profile_id", flat=True):
            counts[pid] = counts.get(pid, 0) + 1
        for profile in items:
            profile.account_count = counts.get(profile.pk, 0)
        return render(request, "profiles/select.html", {"profiles": items, "page_title": "Escolher perfil"})


class ProfileEnterView(View):
    http_method_names = ["post", "options"]

    def post(self, request, pk):
        profile = get_object_or_404(Profile, pk=pk, owner=request.user)
        request.session.pop(profiles.WIZARD_KEY, None)
        profiles.activate(request, profile)
        return redirect("dashboard:index")


class ProfileNewView(View):
    """Passo 1 do wizard: nome. Confirmar cria o Perfil, ativa-o e segue para as redes."""

    def _render(self, request, form, status=200):
        return render(
            request,
            "profiles/wizard_name.html",
            {"form": form, "steps": STEPS, "step": 1, "page_title": "Novo perfil"},
            status=status,
        )

    def get(self, request):
        return self._render(request, ProfileForm(owner=request.user))

    def post(self, request):
        form = ProfileForm(request.POST, owner=request.user)
        if not form.is_valid():
            return self._render(request, form, status=200)
        profile = Profile.objects.create(owner=request.user, name=form.cleaned_data["name"])
        profiles.start_wizard(request, profile)
        return redirect("social:profile_connect", pk=profile.pk)


class ProfileConnectView(View):
    """Passo 2: ícones das redes para conectar. "Concluir" segue ao dashboard."""

    def get(self, request, pk):
        profile = get_object_or_404(Profile, pk=pk, owner=request.user)
        profiles.start_wizard(request, profile)  # garante o perfil ativo e o retorno ao wizard após o OAuth
        networks = [
            {"key": "facebook", "label": "Facebook", "icon": "facebook", "hint": "Páginas que você administra", "kind": "post",
             "url": "social:facebook_connect", "enabled": meta_configured()},
            {"key": "instagram", "label": "Instagram", "icon": "instagram", "hint": "Via Página do Facebook vinculada", "kind": "post",
             "url": "social:facebook_connect", "enabled": meta_configured()},
            {"key": "threads", "label": "Threads", "icon": "at-sign", "hint": "Seu perfil do Threads", "kind": "post",
             "url": "social:threads_connect", "enabled": threads_configured()},
            {"key": "whatsapp", "label": "WhatsApp", "icon": "message-circle", "hint": "Status via Evolution", "kind": "link",
             "url": "social:whatsapp_new", "enabled": evolution_configured()},
            {"key": "twitter", "label": "Twitter / X", "icon": "twitter", "hint": "Em breve", "kind": "soon", "enabled": False},
            {"key": "tiktok", "label": "TikTok", "icon": "music-2", "hint": "Em breve", "kind": "soon", "enabled": False},
        ]
        accounts = SocialAccount.objects.filter(owner=request.user, profile=profile).select_related("parent")
        return render(
            request,
            "profiles/wizard_connect.html",
            {"profile": profile, "networks": networks, "accounts": accounts, "steps": STEPS, "step": 2, "page_title": "Conectar redes"},
        )


class ProfileDoneView(View):
    """Passo 3: concluir (as redes também podem ser conectadas depois)."""

    http_method_names = ["post", "options"]

    def post(self, request, pk):
        profile = get_object_or_404(Profile, pk=pk, owner=request.user)
        request.session.pop(profiles.WIZARD_KEY, None)
        profiles.activate(request, profile)
        return redirect("dashboard:index")
