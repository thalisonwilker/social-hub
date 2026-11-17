"""Navegação da sidebar, definida em um único lugar."""

NAV_ITEMS = [
    {"label": "Dashboard", "icon": "layout-dashboard", "url": "dashboard:index", "prefixes": ("dashboard:",)},
    {"label": "Contas conectadas", "icon": "share-2", "url": "social:accounts", "prefixes": ("social:account", "social:facebook")},
    {"label": "Publicações", "icon": "file-text", "url": "social:posts", "prefixes": ("social:post",)},
    {"label": "Agenda", "icon": "calendar-days", "url": "social:calendar", "prefixes": ("social:calendar",)},
]

NAV_FOOTER = [
    {"label": "Minha conta", "icon": "settings", "url": "accounts:profile", "prefixes": ("accounts:",)},
]


def _mark_active(items, match):
    """Marca o item ativo pelo prefixo de `namespace:url_name` (ex.: `social:post_detail` ativa Publicações)."""
    full = ""
    if match is not None:
        namespace = match.namespaces[0] if match.namespaces else ""
        full = f"{namespace}:{match.url_name}"
    return [{**item, "active": any(full.startswith(prefix) for prefix in item["prefixes"])} for item in items]


def navigation(request):
    match = getattr(request, "resolver_match", None)
    return {
        "nav_items": _mark_active(NAV_ITEMS, match),
        "nav_footer": _mark_active(NAV_FOOTER, match),
    }
