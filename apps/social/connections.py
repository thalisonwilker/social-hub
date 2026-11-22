"""Central de conexões (spec 0017): monta, por rede, o que a tela `/contas/` mostra.

Nada aqui faz rede: só lê as contas já carregadas, a contagem de publicações do Hub e a configuração.
"""
from dataclasses import dataclass, field

from django.db.models import Count
from django.urls import reverse

from .conf import evolution_configured, meta_configured, threads_configured
from .models import PublicationTarget, SocialAccount

P = SocialAccount.Platform


@dataclass(frozen=True)
class Network:
    slug: str  # valor de `?rede=`
    label: str
    platform: str
    icon: str  # nome do ícone lucide
    hint: str  # linha de apoio do painel desconectado
    not_configured: str  # linha de apoio quando a integração da rede não está configurada


NETWORKS = (
    Network("facebook", "Facebook", P.FACEBOOK_PAGE, "facebook", "Conecte as Páginas que você administra.",
            "Integração com a Meta não configurada"),
    Network("instagram", "Instagram", P.INSTAGRAM, "instagram", "O Instagram é conectado pela sua Página do Facebook.",
            "Integração com a Meta não configurada"),
    Network("threads", "Threads", P.THREADS, "at-sign", "Conecte o seu perfil do Threads.",
            "Integração com o Threads não configurada"),
    Network("whatsapp", "WhatsApp", P.WHATSAPP_STATUS, "message-circle", "Adicione uma instância para publicar no Status.",
            "Integração com o WhatsApp não configurada"),
)
SLUG_BY_PLATFORM = {n.platform: n.slug for n in NETWORKS}

# Estado do ícone (Matriz de decisão do AC-2)
DISCONNECTED, CONNECTED, NEEDS_REAUTH = "disconnected", "connected", "needs_reauth"
STATE_LABELS = {DISCONNECTED: "desconectada", CONNECTED: "conectada", NEEDS_REAUTH: "reconexão necessária"}


def accounts_url(platform: str | None = None) -> str:
    """`/contas/?rede=<rede>` da plataforma (ou `/contas/` sem plataforma conhecida)."""
    url = reverse("social:accounts")
    slug = SLUG_BY_PLATFORM.get(platform)
    return f"{url}?rede={slug}" if slug else url


@dataclass
class Connect:
    """Como conectar/reconectar uma rede: POST para `url` (OAuth) ou GET (link) para o WhatsApp."""

    url: str
    method: str  # "post" | "get"
    enabled: bool


@dataclass
class NetworkPanel:
    network: Network
    accounts: list = field(default_factory=list)
    configured: bool = True
    connect: Connect | None = None
    selected: bool = False

    @property
    def state(self) -> str:
        if not self.accounts:
            return DISCONNECTED
        if any(a.needs_reauth for a in self.accounts):
            return NEEDS_REAUTH
        return CONNECTED

    @property
    def state_label(self) -> str:
        return STATE_LABELS[self.state]

    @property
    def aria_label(self) -> str:
        return f"{self.network.label} — {self.state_label}"


def _connect_for(network: Network, configured: dict) -> Connect:
    if network.platform == P.WHATSAPP_STATUS:
        return Connect(reverse("social:whatsapp_new"), "get", configured["evolution"])
    if network.platform == P.THREADS:
        return Connect(reverse("social:threads_connect"), "post", configured["threads"])
    # Facebook e Instagram (o Instagram vem pela Página — ADR-0013)
    return Connect(reverse("social:facebook_connect"), "post", configured["meta"])


def reconnect_url(account: SocialAccount, connect: Connect) -> str:
    if account.platform == P.WHATSAPP_STATUS:
        return f"{connect.url}?instance={account.external_id}"
    return connect.url


def build_panels(accounts, requested: str | None) -> list[NetworkPanel]:
    """Um painel por rede, na ordem fixa, com a rede selecionada marcada (AC-4)."""
    configured = {"meta": meta_configured(), "threads": threads_configured(), "evolution": evolution_configured()}
    accounts = list(accounts)
    published = dict(
        PublicationTarget.objects.filter(account__in=accounts, status=PublicationTarget.Status.PUBLISHED)
        .order_by()
        .values_list("account")
        .annotate(n=Count("pk"))
    )
    panels = []
    for network in NETWORKS:
        mine = sorted((a for a in accounts if a.platform == network.platform), key=lambda a: a.name.casefold())
        connect = _connect_for(network, configured)
        for account in mine:
            account.published_count = published.get(account.pk, 0)
            account.reconnect_url = reconnect_url(account, connect)
        panels.append(NetworkPanel(network, mine, connect.enabled, connect))

    slugs = {p.network.slug: p for p in panels}
    chosen = slugs.get(requested or "") or next((p for p in panels if p.accounts), panels[0])
    chosen.selected = True
    return panels
