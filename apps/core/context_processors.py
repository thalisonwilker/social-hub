"""Navegação da sidebar, definida em um único lugar."""

NAV_ITEMS = [
    {"label": "Dashboard", "icon": "layout-dashboard", "url": "dashboard:index", "section": "dashboard"},
    {"label": "Contas conectadas", "icon": "share-2", "url": "social:accounts", "section": "social:accounts"},
    {"label": "Publicações", "icon": "file-text", "url": "social:posts", "section": "social:posts"},
    {"label": "Agenda", "icon": "calendar-days", "url": "social:calendar", "section": "social:calendar"},
]

NAV_FOOTER = [
    {"label": "Minha conta", "icon": "settings", "url": "accounts:profile", "section": "accounts"},
]


def _mark_active(items, match):
    current = ""
    if match:
        current = match.namespaces[0] if match.namespaces else match.url_name
        full = f"{current}:{match.url_name}"
    else:
        full = ""
    return [
        {**item, "active": item["section"] in (current, full)}
        for item in items
    ]


def navigation(request):
    match = getattr(request, "resolver_match", None)
    return {
        "nav_items": _mark_active(NAV_ITEMS, match),
        "nav_footer": _mark_active(NAV_FOOTER, match),
    }
