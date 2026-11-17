"""Dados DEMONSTRATIVOS da dashboard.

Nada aqui vem de APIs reais. Quando as integrações existirem, substitua estas
funções por consultas aos modelos/serviços do app `social`, mantendo o formato
de retorno para não alterar o template.
"""


def _sparkline(values, width=96, height=28):
    """Converte uma série em pontos de polyline SVG."""
    low, high = min(values), max(values)
    span = (high - low) or 1
    step = width / (len(values) - 1)
    return " ".join(
        f"{i * step:.1f},{height - 2 - (v - low) / span * (height - 4):.1f}"
        for i, v in enumerate(values)
    )


def kpis():
    items = [
        {"label": "Seguidores", "value": "48,2 mil", "delta": 3.4, "icon": "users", "series": [30, 32, 31, 35, 38, 41, 44]},
        {"label": "Alcance (30 dias)", "value": "312 mil", "delta": 12.1, "icon": "eye", "series": [20, 26, 24, 31, 29, 36, 40]},
        {"label": "Engajamento", "value": "4,8%", "delta": -0.6, "icon": "heart", "series": [40, 38, 41, 37, 36, 35, 34]},
        {"label": "Publicações no mês", "value": "27", "delta": 8.0, "icon": "send", "series": [10, 12, 14, 13, 18, 21, 27]},
    ]
    for item in items:
        item["positive"] = item["delta"] >= 0
        item["sparkline"] = _sparkline(item["series"])
    return items


def weekly_reach():
    data = [("Seg", 31), ("Ter", 44), ("Qua", 38), ("Qui", 57), ("Sex", 63), ("Sáb", 41), ("Dom", 29)]
    top = max(v for _, v in data)
    return [
        {"day": day, "value": f"{value} mil", "pct": round(value / top * 100)}
        for day, value in data
    ]


def platforms():
    return [
        {"name": "Facebook", "icon": "facebook", "share": 38, "connected": False},
        {"name": "Instagram", "icon": "instagram", "share": 46, "connected": False},
        {"name": "Threads", "icon": "at-sign", "share": 16, "connected": False},
    ]


def recent_posts():
    return [
        {"title": "Lançamento da coleção de verão", "platform": "Instagram", "status": "published", "status_label": "Publicado", "reach": "18,4 mil", "date": "12/11"},
        {"title": "Bastidores da equipe", "platform": "Facebook", "status": "published", "status_label": "Publicado", "reach": "6,1 mil", "date": "10/11"},
        {"title": "Enquete: próximo produto", "platform": "Threads", "status": "scheduled", "status_label": "Agendado", "reach": "—", "date": "19/11"},
        {"title": "Promoção de fim de ano", "platform": "Instagram", "status": "draft", "status_label": "Rascunho", "reach": "—", "date": "—"},
    ]
