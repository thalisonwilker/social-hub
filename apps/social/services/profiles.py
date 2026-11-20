"""Perfil ativo na sessão e vínculo das contas ao Perfil (spec 0011)."""
from django.db.models import Q
from django.urls import reverse

from apps.social.models import Profile, SocialAccount

ACTIVE_KEY = "active_profile_id"
WIZARD_KEY = "profile_wizard_id"  # perfil em criação: a conexão devolve ao wizard/dashboard


def get_active(request) -> Profile | None:
    """Perfil ativo do usuário logado; ignora (e limpa) um id que não é dele."""
    pk = request.session.get(ACTIVE_KEY)
    if not pk or not request.user.is_authenticated:
        return None
    profile = Profile.objects.filter(pk=pk, owner=request.user).first()
    if profile is None:
        request.session.pop(ACTIVE_KEY, None)
    return profile


def activate(request, profile: Profile) -> None:
    request.session[ACTIVE_KEY] = profile.pk


def deactivate(request) -> None:
    request.session.pop(ACTIVE_KEY, None)
    request.session.pop(WIZARD_KEY, None)


def start_wizard(request, profile: Profile) -> None:
    activate(request, profile)
    request.session[WIZARD_KEY] = profile.pk


def scope(request, queryset):
    """Restringe contas ao Perfil ativo; sem Perfil ativo nada muda (usuário que ainda não usa Perfis)."""
    profile = get_active(request)
    return queryset.filter(profile=profile) if profile else queryset


def adopt(request, accounts) -> None:
    """Vincula ao Perfil ativo as contas (e as Instagram ligadas a elas) que ainda não têm Perfil."""
    profile = get_active(request)
    if profile is None:
        return
    ids = [a.pk for a in accounts]
    if not ids:
        return
    SocialAccount.objects.filter(owner=request.user, profile__isnull=True).filter(
        Q(pk__in=ids) | Q(parent__in=ids)
    ).update(profile=profile)


def after(request, *, ok: bool = False) -> str:
    """Para onde voltar depois de uma conexão: no wizard, sucesso → dashboard, falha → passo 2."""
    pk = request.session.get(WIZARD_KEY)
    if pk and get_active(request) and get_active(request).pk == pk:
        if ok:
            request.session.pop(WIZARD_KEY, None)
            return reverse("dashboard:index")
        return reverse("social:profile_connect", args=[pk])
    return reverse("social:accounts")
