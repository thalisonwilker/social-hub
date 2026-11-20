"""Views de publicação (texto + imagem em várias Páginas). Ver specs/0003-publicar-no-facebook."""
import logging

from django.conf import settings
from django.contrib import messages
from django.db import DatabaseError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from .conf import evolution_configured, meta_configured, publish_in_background, threads_configured
from .forms import PublicationForm
from . import views_ai
from .services import gemini
from .models import Publication, SocialAccount, WorkerHeartbeat
from .services import deletion, profiles, publishing, threads_tokens

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
MSG_REMOVED = "Publicação removida do Hub."
MSG_TARGET_REMOVED = "Destino removido do Hub."
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
        SocialAccount.Platform.INSTAGRAM: "Integração com a Meta não configurada",
    }

    def _configured(self):
        return {
            SocialAccount.Platform.FACEBOOK_PAGE: meta_configured(),
            SocialAccount.Platform.THREADS: threads_configured(),
            SocialAccount.Platform.WHATSAPP_STATUS: evolution_configured(),
            SocialAccount.Platform.INSTAGRAM: meta_configured(),
        }

    def _destinations(self, request):
        """Contas do usuário anotadas com `selectable` (ativa e com a plataforma configurada) e o motivo de não estar."""
        threads_tokens.expire_stale_tokens(request.user)  # contas com token vencido não podem ser alvo
        configured = self._configured()
        accounts = list(
            profiles.scope(
                request,
                SocialAccount.objects.filter(
                    owner=request.user,
                    platform__in=[
                        SocialAccount.Platform.FACEBOOK_PAGE,
                        SocialAccount.Platform.THREADS,
                        SocialAccount.Platform.WHATSAPP_STATUS,
                        SocialAccount.Platform.INSTAGRAM,
                    ],
                ),
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
        instagram = [a for a in accounts if a.platform == SocialAccount.Platform.INSTAGRAM]
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
                ("Contas do Instagram", "instagram", instagram),
            ],
            "instagram_accounts": instagram,
            "selected": set(request.POST.getlist("accounts")),
            "blocked": blocked,
            "confirm_message": CONFIRM,
            "ai_models": gemini.allowed_models(),
            "ai_text_providers": [
                {"id": pid, "label": label, "model": model, "key": views_ai.key_status(request.user, pid)}
                for pid, label, model in (
                    ("gemini", "Google Gemini", settings.GEMINI_TEXT_MODEL),
                    ("deepseek", "DeepSeek", settings.DEEPSEEK_TEXT_MODEL),
                )
                if model
            ],
            "ai_example_prompt": views_ai.EXAMPLE_TEXT_PROMPT,
            "ai_key": views_ai.key_status(request.user),
            "generated_image_id": request.POST.get("generated_image", "") if request.method == "POST" else "",
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
        background = publish_in_background()
        in_progress = any(t.status in (publishing.S.PENDING, publishing.S.SENDING) for t in targets)
        if background:  # só "Tentar novamente" (failed → fila); "Continuar envio" não existe neste modo (spec 0007)
            can_send = has_failed = any(t.can_try_again for t in targets)
        else:
            can_send = any(t.is_retryable for t in targets)
            has_failed = any(t.status == "failed" and t.is_retryable for t in targets)
        for target in targets:  # spec 0010: o que dá (ou não) para apagar na plataforma
            target.delete_reason = deletion.eligibility(target) if target.status == publishing.S.PUBLISHED else ""
            target.can_delete_remote = target.status == publishing.S.PUBLISHED and not target.delete_reason
        context = {
            "can_delete_any": any(t.can_delete_remote for t in targets),
            "page_title": f"Publicação #{publication.pk}",
            "publication": publication,
            "targets": targets,
            "counts": publication.status_counts(),
            "can_send": can_send,
            "has_failed": has_failed,
            "worker_mode": background,
            # Polling só enquanto há alvo na fila/enviando; com tudo terminado a página não traz o atributo (nenhuma consulta).
            "poll": in_progress,
            "poll_signature": "|".join(f"{t.pk}:{t.status}" for t in targets),
            "worker_warning": background and in_progress and not WorkerHeartbeat.is_active(),
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


def _report_delete(request, result):
    level = {"deleted": messages.success, "already_gone": messages.info, "unknown": messages.warning}.get(result.outcome, messages.error)
    level(request, result.message)


class PostRemoveView(View):
    """"Remover do Hub": apaga a publicação, os alvos e a imagem (não chama plataforma). Só POST, só o dono (spec 0010)."""

    http_method_names = ["post", "options"]

    def post(self, request, pk):
        publication = get_publication_or_404(request, pk)
        if deletion.remove_publication(publication):
            messages.success(request, MSG_REMOVED)
            return redirect("social:posts")
        messages.error(request, deletion.MSG_REMOVE_SENDING)
        return redirect("social:post_detail", pk=publication.pk)


class TargetRemoveView(View):
    """"Remover do Hub" de um destino; o último remove a publicação. Só POST, só o dono."""

    http_method_names = ["post", "options"]

    def post(self, request, pk, target_pk):
        publication = get_publication_or_404(request, pk)
        target = get_object_or_404(publication.targets.select_related("publication"), pk=target_pk)
        outcome = deletion.remove_target(target)
        if outcome == "publication":
            messages.success(request, MSG_REMOVED)
            return redirect("social:posts")
        if outcome == "target":
            messages.success(request, MSG_TARGET_REMOVED)
        else:
            messages.error(request, deletion.MSG_REMOVE_SENDING)
        return redirect("social:post_detail", pk=publication.pk)


class TargetDeleteRemoteView(View):
    """"Apagar na plataforma" um destino (Facebook/Threads). Só POST, só o dono. Não remove o registro."""

    http_method_names = ["post", "options"]

    def post(self, request, pk, target_pk):
        publication = get_publication_or_404(request, pk)
        target = get_object_or_404(publication.targets.select_related("account"), pk=target_pk)
        _report_delete(request, deletion.delete_on_platform(target))
        return redirect("social:post_detail", pk=publication.pk)


class PostDeleteRemoteView(View):
    """"Apagar na plataforma (todos possíveis)": tenta cada destino apagável e resume o resultado."""

    http_method_names = ["post", "options"]

    def post(self, request, pk):
        publication = get_publication_or_404(request, pk)
        bulk = deletion.delete_publication_on_platform(publication)
        summary = f"{bulk.deleted} apagado(s), {bulk.failed} com falha e {bulk.skipped} sem exclusão pelo Hub."
        (messages.success if bulk.deleted and not bulk.failed else messages.warning)(request, summary)
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
