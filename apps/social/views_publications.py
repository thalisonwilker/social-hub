"""Views de publicação (texto + imagem em várias Páginas). Ver specs/0003-publicar-no-facebook."""
import logging

from django.contrib import messages
from django.db import DatabaseError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from .conf import meta_configured, threads_configured
from .forms import PublicationForm
from .models import Publication, SocialAccount
from .services import publishing, threads_tokens

logger = logging.getLogger("apps.social.meta")

MSG_NOT_CONFIGURED = "Integração com a Meta não configurada."
MSG_NO_ACTIVE_PAGES = "Conecte ao menos uma Página ativa ou um perfil do Threads antes de publicar."
MSG_THREADS_NOT_CONFIGURED = "Integração com o Threads não configurada."
MSG_THREADS_IMAGE_IGNORED = "No Threads, apenas o texto é publicado: a imagem foi ignorada."
MSG_SAVE_FAILED = "Não foi possível salvar a publicação. Tente novamente."
CONFIRM = "Será publicado de verdade nas Páginas selecionadas. Continuar?"


def user_publications(user):
    return Publication.objects.filter(owner=user).prefetch_related("targets")


def get_publication_or_404(request, pk) -> Publication:
    return get_object_or_404(user_publications(request.user), pk=pk)


def report_batch(request, result):
    """Mensagem resumindo o resultado do lote."""
    if result.attempted == 0 and result.remaining == 0:
        messages.info(request, "Nada a enviar: não há Páginas pendentes ou com falha que possam ser reenviadas.")
        return
    if result.failed == 0:
        count = result.published
        messages.success(request, f"Publicado em {count} Página." if count == 1 else f"Publicado em {count} Páginas.")
    else:
        messages.warning(request, f"{result.published} publicada(s) e {result.failed} com falha. Veja os detalhes abaixo.")
    if result.remaining:
        messages.info(request, f"{result.remaining} Página(s) ainda pendente(s). Use “Continuar envio”.")


class PostsView(TemplateView):
    """Histórico de publicações do usuário."""

    template_name = "social/posts.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(page_title="Publicações", publications=user_publications(self.request.user))
        return context


class PostNewView(View):
    template_name = "social/post_form.html"

    PLATFORM_LABELS = {
        SocialAccount.Platform.FACEBOOK_PAGE: "Integração com a Meta não configurada",
        SocialAccount.Platform.THREADS: MSG_THREADS_NOT_CONFIGURED,
    }

    def _configured(self):
        return {
            SocialAccount.Platform.FACEBOOK_PAGE: meta_configured(),
            SocialAccount.Platform.THREADS: threads_configured(),
        }

    def _destinations(self, request):
        """Contas do usuário anotadas com `selectable` (ativa e com a plataforma configurada) e o motivo de não estar."""
        threads_tokens.expire_stale_tokens(request.user)  # contas com token vencido não podem ser alvo
        configured = self._configured()
        accounts = list(
            SocialAccount.objects.filter(
                owner=request.user,
                platform__in=[SocialAccount.Platform.FACEBOOK_PAGE, SocialAccount.Platform.THREADS],
            )
        )
        for account in accounts:
            if account.needs_reauth:
                account.unavailable_reason = "Reconexão necessária"
            elif not configured[account.platform]:
                account.unavailable_reason = "Integração não configurada"
            else:
                account.unavailable_reason = ""
            account.selectable = not account.unavailable_reason
        return accounts

    def _blocked_reason(self, accounts):
        if any(a.selectable for a in accounts):
            return None
        active = [a for a in accounts if a.status == SocialAccount.Status.ACTIVE]
        if active:  # há contas ativas, mas a integração da plataforma delas não está configurada
            return self.PLATFORM_LABELS[active[0].platform] + "."
        return MSG_NO_ACTIVE_PAGES

    def _render(self, request, form, accounts, *, blocked=None, status=200):
        facebook = [a for a in accounts if a.platform == SocialAccount.Platform.FACEBOOK_PAGE]
        threads = [a for a in accounts if a.platform == SocialAccount.Platform.THREADS]
        context = {
            "page_title": "Nova publicação",
            "form": form,
            "facebook_accounts": facebook,
            "threads_accounts": threads,
            "destination_groups": [("Páginas do Facebook", "facebook", facebook), ("Perfis do Threads", "at-sign", threads)],
            "selected": set(request.POST.getlist("accounts")),
            "blocked": blocked,
            "confirm_message": CONFIRM,
            "max_text": PublicationForm.base_fields["text"].max_length,
        }
        return render(request, self.template_name, context, status=status)

    def _form(self, request, accounts, *args):
        platforms = {a.platform for a in accounts if a.selectable}
        return PublicationForm(*args, user=request.user, platforms=platforms)

    def get(self, request):
        accounts = self._destinations(request)
        blocked = self._blocked_reason(accounts)
        return self._render(request, None if blocked else self._form(request, accounts), accounts, blocked=blocked)

    def post(self, request):
        accounts = self._destinations(request)
        blocked = self._blocked_reason(accounts)
        if blocked:
            messages.error(request, blocked)
            return redirect("social:accounts")

        form = self._form(request, accounts, request.POST, request.FILES)
        if not form.is_valid():
            return self._render(request, form, accounts)

        try:
            publication = publishing.create_publication(
                request.user, form.cleaned_data["text"], form.sanitized, list(form.cleaned_data["accounts"])
            )
        except (OSError, DatabaseError):
            form.add_error(None, MSG_SAVE_FAILED)
            return self._render(request, form, accounts, status=500)

        if form.image_ignored:
            messages.info(request, MSG_THREADS_IMAGE_IGNORED)
        report_batch(request, publishing.send_pending(publication))
        return redirect("social:post_detail", pk=publication.pk)


class PostDetailView(View):
    def get(self, request, pk):
        publication = get_publication_or_404(request, pk)
        targets = list(publication.targets.all())
        context = {
            "page_title": f"Publicação #{publication.pk}",
            "publication": publication,
            "targets": targets,
            "counts": publication.status_counts(),
            "can_send": any(t.is_retryable for t in targets),
            "has_failed": any(t.status == "failed" and t.is_retryable for t in targets),
            "confirm_message": CONFIRM,
        }
        return render(request, "social/post_detail.html", context)


class PostSendView(View):
    """Continua o envio (pendentes) e tenta de novo as falhas. Só POST."""

    http_method_names = ["post", "options"]

    def post(self, request, pk):
        publication = get_publication_or_404(request, pk)
        if not meta_configured():
            messages.error(request, MSG_NOT_CONFIGURED)
            return redirect("social:post_detail", pk=publication.pk)
        report_batch(request, publishing.send_pending(publication))
        return redirect("social:post_detail", pk=publication.pk)


class PostImageView(View):
    """Entrega a imagem só ao dono; não existe URL pública de mídia (ADR-0005)."""

    def get(self, request, pk):
        publication = get_publication_or_404(request, pk)
        if not publication.has_image:
            raise Http404("Esta publicação não tem imagem.")
        try:
            handle = publication.image.open("rb")
        except FileNotFoundError:
            raise Http404("Imagem indisponível.") from None
        response = FileResponse(handle, content_type=publication.image_content_type)
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, max-age=3600"
        response["Content-Disposition"] = "inline"
        return response
