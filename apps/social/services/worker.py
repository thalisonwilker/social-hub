"""Worker de envio (spec 0007): reivindica um alvo `pending` por vez e o envia fora da requisição HTTP.

- Fila = os próprios alvos `pending`, em ordem de criação (FIFO por id). Sem orçamento por requisição: usa o timeout de cada chamada.
- Na PARTIDA todo alvo `sending` vira `uncertain` (`worker_restart`): com um único worker, nenhum deles tem dono vivo.
- A cada ciclo: batida (heartbeat) e *reaper* de `sending` vencido (→ `uncertain`, `stale`). Nunca reenvia sozinho.
- SIGTERM/SIGINT: termina o alvo atual e sai. Logs só com ids, plataforma e estado — nunca chave, texto ou corpo.
"""
import logging
import os
import signal
import threading

from django.conf import settings
from django.db import OperationalError, close_old_connections

from apps.social.models import PublicationTarget, WorkerHeartbeat

from . import publishing

logger = logging.getLogger("apps.social.meta")
S = PublicationTarget.Status


class Worker:
    def __init__(self, *, pool: publishing.ClientPool | None = None, sleep=None, pid: int | None = None):
        self.pool = pool or publishing.ClientPool()
        self.pid = pid if pid is not None else os.getpid()
        self.stop_event = threading.Event()
        self._sleep = sleep  # injetável nos testes; padrão: espera interrompível pelo stop_event

    # --- ciclo de vida ----------------------------------------------------------------
    def start(self) -> int:
        """Partida: registra o heartbeat e manda todo alvo `sending` para `uncertain` (`worker_restart`)."""
        WorkerHeartbeat.start(pid=self.pid)
        recovered = publishing.recover_sending(reason="worker_restart")
        logger.info("worker_started pid=%d", self.pid)
        if recovered:
            logger.warning("worker_recovered n=%d", recovered)
        return recovered

    def request_stop(self) -> None:
        self.stop_event.set()

    def install_signal_handlers(self) -> None:
        """SIGTERM/SIGINT pedem parada: o alvo em andamento termina e o laço sai."""
        def handler(signum, frame):  # noqa: ARG001
            logger.info("worker_stop_requested")
            self.request_stop()

        signal.signal(signal.SIGTERM, handler)
        signal.signal(signal.SIGINT, handler)

    def run(self, *, max_cycles: int | None = None) -> int:
        """Laço principal. Devolve quantos alvos foram processados. `max_cycles` limita os ciclos (testes)."""
        self.start()
        processed = cycles = 0
        while not self.stop_event.is_set():
            if max_cycles is not None and cycles >= max_cycles:
                break
            cycles += 1
            result = self.run_once()
            if result is None:
                self._idle()
            else:
                processed += 1
        logger.info("worker_stopped processed=%d", processed)
        return processed

    def _idle(self) -> None:
        wait = settings.WORKER_POLL_SECONDS
        if self._sleep is not None:
            self._sleep(wait)
        else:
            self.stop_event.wait(wait)

    # --- um ciclo ---------------------------------------------------------------------
    def run_once(self) -> str | None:
        """Um ciclo: heartbeat, reaper e no máximo UM alvo. Devolve o estado final do alvo processado, ou None (fila vazia/ocupada)."""
        close_old_connections()  # processo longo: não segura conexão velha
        try:
            WorkerHeartbeat.beat(pid=self.pid)
            publishing.recover_stale_sending()
            target = self._next_pending()
            if target is None:
                return None
            if target.account_id is None:  # conta desconectada: falha sem chamar a plataforma (não trava a fila)
                publishing.mark_disconnected(target)
                return S.FAILED
            claimed = publishing.claim_target(target.pk)
            if claimed is None:  # outro processo o levou, ou o banco estava travado: tenta no próximo ciclo
                return None
            logger.info("worker_target_claimed target=%s platform=%s", claimed.pk, claimed.platform)
            return self._process(claimed)
        except OperationalError:  # `database is locked`: nenhuma transição se perde; repete no ciclo seguinte
            logger.warning("worker_db_locked")
            return None
        finally:
            try:
                WorkerHeartbeat.beat(pid=self.pid)
            except OperationalError:
                pass

    def _next_pending(self) -> PublicationTarget | None:
        return PublicationTarget.objects.filter(status=S.PENDING).select_related("account").order_by("id").first()

    def _process(self, claimed: PublicationTarget) -> str:
        try:
            status = publishing.dispatch_claimed(claimed, self.pool)  # sem orçamento: timeout de cada chamada
        except Exception as exc:  # noqa: BLE001 — um bug não pode derrubar o worker nem deixar o alvo preso
            logger.error("worker_error target=%s type=%s", claimed.pk, type(exc).__name__)  # nunca a mensagem (pode ter segredos)
            publishing.mark_unexpected_error(claimed.pk)
            return S.UNCERTAIN
        logger.info("worker_target_done target=%s status=%s", claimed.pk, status)
        return status
