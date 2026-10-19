from django.core.management.base import BaseCommand

from cards.catalog_sync import run_sync


class Command(BaseCommand):
    help = "Sincroniza el catálogo desde DragonBall-EnhancedAPI (solo lo nuevo o cambiado)."

    def add_arguments(self, parser):
        parser.add_argument("--full", action="store_true", help="Pide el catálogo completo")

    def handle(self, *args, full: bool, **options):
        sync = run_sync(full=full)
        line = (
            f"{sync.status}: {sync.fetched} registros, {sync.created} nuevas, {sync.updated} cambiadas, "
            f"{sync.fingerprints} fingerprints ({sync.fingerprint_errors} errores)"
        )
        if sync.error:
            line += f" | {sync.error}"
        self.stdout.write(self.style.SUCCESS(line) if sync.status == "success" else self.style.ERROR(line))
