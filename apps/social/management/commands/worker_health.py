"""Healthcheck do worker (spec 0007): sai com 0 se o heartbeat é recente e com 1 caso contrário."""
import sys

from django.core.management.base import BaseCommand

from apps.social.models import PublicationTarget, WorkerHeartbeat


class Command(BaseCommand):
    help = "Código 0 se o worker de envio está ativo (batida recente); 1 se não. Mostra o tamanho da fila."

    def handle(self, *args, **options):
        S = PublicationTarget.Status
        queue = PublicationTarget.objects.filter(status=S.PENDING).count()
        sending = PublicationTarget.objects.filter(status=S.SENDING).count()
        if WorkerHeartbeat.is_active():
            self.stdout.write(f"worker ativo; fila={queue} enviando={sending}")
            return
        self.stderr.write(f"worker inativo; fila={queue} enviando={sending}")
        sys.exit(1)
