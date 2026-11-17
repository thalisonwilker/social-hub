"""Views de publicação (texto + imagem em várias Páginas). Ver specs/0003-publicar-no-facebook."""
import logging

from django.contrib import messages
from django.db import DatabaseError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from .conf import evolution_configured, meta_configured, publish_in_background, threads_configured
from .forms import PublicationForm
from .models import Publication, SocialAccount, WorkerHeartbeat
from .services import publishing, threads_tokens

logger = logging.getLogger("apps.social.meta")

MSG_NOT_CONFIGURED = "Integração com a Meta não configurada."
MSG_NO_ACTIVE_PAGES = "Conecte ao menos uma Página ativa, um perfil do Threads ou um número de WhatsApp antes de publicar."
MSG_THREADS_NOT_CONFIGURED = "Integração com o Threads não configurada."
MSG_WHATSAPP_NOT_CONFIGURED = publishing.MSG_WHATSAPP_NOT_CONFIGURED
MSG_SAVE_FAILED = "Não foi possível salvar a publicação. Tente novamente."
MSG_QUEUED = "Publicação enfileirada: o envio acontece em segundo plano."
MSG_REQUEUED = "Reenvio enfileirado: o envio acontece em segundo plano."
MSG_NOTHING_TO_REQUEUE = "Nada a reenviar: não há alvos com falha que possam voltar para a fila."
MSG_NOT_UNCERTAIN = "Este alvo não está incerto: nada foi alterado."
MSG_RESOLVED_PUBLISHED = "Marcado como já publicado."
MSG_RESOLVED_RESEND = "Reenvio enfileirado: o envio acontece em segundo plano."
MSG_RESEND_NEEDS_ACCOUNT = "Este alvo não tem conta conectada: só dá para marcar como já publicado."
MSG_UNKNOWN_ACTION = "Ação desconhecida: nada foi alterado."
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
    if result.failed == 0 and result.uncertain == 0:
        count = result.published
        messages.success(request, f"Publicado em {count} Página." if count == 1 else f"Publicado em {count} Páginas.")
    elif result.failed == 0:  # só incertos: o Hub não sabe se a plataforma publicou (spec 0007)
        messages.warning(
            request,
            f"{result.published} publicada(s) e {result.uncertain} incerta(s). Confira na plataforma e resolva abaixo.",
        )
    elif result.uncertain == 0:
        messages.warning(request, f"{result.published} publicada(s) e {result.failed} com falha. Veja os detalhes abaixo.")
    else:
        messages.warning(
            request,
            f"{result.published} publicada(s), {result.failed} com falha e {result.uncertain} incerta(s). Veja os detalhes abaixo.",
        )
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
        SocialAccount.Platform.WHATSAPP_STATUS: MSG_WHATSAPP_NOT_CONFIGURED,
    }

    def _configured(self):
        return {
            SocialAccount.Platform.FACEBOOK_PAGE: meta_configured(),
            SocialAccount.Platform.THREADS: threads_configured(),
            SocialAccount.Platform.WHATSAPP_STATUS: evolution_configured(),
        }

    def _destinations(self, request):
        """Contas do usuário anotadas com `selectable` (ativa e com a plataforma configurada) e o motivo de não estar."""
        threads_tokens.expire_stale_tokens(request.user)  # contas com token vencido não podem ser alvo
        configured = self._configured()
        accounts = list(
            SocialAccount.objects.filter(
                owner=request.user,
                platform__in=[
                    SocialAccount.Platform.FACEBOOK_PAGE,
                    SocialAccount.Platform.THREADS,
                    SocialAccount.Platform.WHATSAPP_STATUS,
                ],
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
        whatsapp = [a for a in accounts if a.platform == SocialAccount.Platform.WHATSAPP_STATUS]
        context = {
            "page_title": "Nova publicação",
            "form": form,
            "facebook_accounts": facebook,
            "threads_accounts": threads,
            "whatsapp_accounts": whatsapp,
            "destination_groups": [
                ("Páginas do Facebook", "facebook", facebook),
                ("Perfis do Threads", "at-sign", threads),
                ("Status do WhatsApp", "message-circle", whatsapp),
            ],
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

        if publish_in_background():  # só enfileira: o worker envia fora da requisição (spec 0007)
            messages.success(request, MSG_QUEUED)
        else:
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
    """"Tentar novamente". Modo `worker`: reenfileira os alvos `failed` (nada é enviado na requisição). Modo `inline`: envia na hora. Só POST."""

    http_method_names = ["post", "options"]

    def post(self, request, pk):
        publication = get_publication_or_404(request, pk)
        if publish_in_background():
            if publishing.requeue_failed(publication):
                messages.success(request, MSG_REQUEUED)
            else:
                messages.info(request, MSG_NOTHING_TO_REQUEUE)
            return redirect("social:post_detail", pk=publication.pk)
        if not meta_configured():
            messages.error(request, MSG_NOT_CONFIGURED)
            return redirect("social:post_detail", pk=publication.pk)
        report_batch(request, publishing.send_pending(publication))
        return redirect("social:post_detail", pk=publication.pk)


class TargetResolveView(View):
    """Resolve um alvo Incerto: "Já foi publicado" ou "Reenviar" (assume o risco de duplicar). Só POST, só o dono."""

    http_method_names = ["post", "options"]

    def post(self, request, pk, target_pk):
        publication = get_publication_or_404(request, pk)
        target = get_object_or_404(publication.targets, pk=target_pk)
        action = request.POST.get("acao", "")
        if action not in ("publicado", "reenviar"):
            messages.error(request, MSG_UNKNOWN_ACTION)
        elif not target.is_resolvable:
            messages.error(request, MSG_NOT_UNCERTAIN)
        elif action == "publicado":
            if publishing.resolve_as_published(target.pk):
                messages.success(request, MSG_RESOLVED_PUBLISHED)
            else:
                messages.error(request, MSG_NOT_UNCERTAIN)
        elif not target.can_resend:
            messages.error(request, MSG_RESEND_NEEDS_ACCOUNT)
        elif publishing.resolve_resend(target.pk):
            if publish_in_background():
                messages.success(request, MSG_RESOLVED_RESEND)
            else:  # modo inline: envia na requisição, como "Tentar novamente"
                report_batch(request, publishing.send_pending(publication))
        else:
            messages.error(request, MSG_NOT_UNCERTAIN)
        return redirect("social:post_detail", pk=publication.pk)


class PostStateView(View):
    """Estado mínimo para o polling da tela (spec 0007): só ids, estados, contagens e se há worker. Sem texto, contas nem mensagens."""

    http_method_names = ["get", "head", "options"]

    def get(self, request, pk):
        publication = get_publication_or_404(request, pk)
        targets = list(publication.targets.all())
        in_progress = {publishing.S.PENDING, publishing.S.SENDING}
        response = JsonResponse(
            {
                "status": publication.status,
                "counts": publication.status_counts(),
                "targets": [{"id": t.pk, "status": t.status} for t in targets],
                "worker": {"active": WorkerHeartbeat.is_active()},
                "done": not any(t.status in in_progress for t in targets),
            }
        )
        response["Cache-Control"] = "no-store"
        return response


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
