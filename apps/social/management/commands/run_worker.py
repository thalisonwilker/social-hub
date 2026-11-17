"""Worker de envio em segundo plano (spec 0007). Uso: `python manage.py run_worker` (container `worker`)."""
from django.core.management.base import BaseCommand

from apps.social.services.worker import Worker


class Command(BaseCommand):
    help = "Envia as publicações pendentes em segundo plano (um alvo por vez). SIGTERM termina o alvo atual e sai."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Executa um único ciclo (batida, reaper e no máximo um alvo) e sai; não faz a recuperação da partida.",
        )

    def handle(self, *args, **options):
        worker = Worker()
        if options["once"]:
            result = worker.run_once()
            self.stdout.write(f"ciclo único: {result or 'fila vazia'}")
            return
        worker.install_signal_handlers()
        self.stdout.write("worker iniciado (SIGTERM encerra depois do alvo atual)")
        processed = worker.run()
        self.stdout.write(f"worker encerrado: {processed} alvo(s) processado(s)")
