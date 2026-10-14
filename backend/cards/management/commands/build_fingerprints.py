from django.core.management.base import BaseCommand

from cards.fingerprints import build_pending


class Command(BaseCommand):
    help = "Descarga las imágenes oficiales y calcula los fingerprints pendientes."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Recalcula todos")
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, force: bool, limit: int | None, **options):
        ok, errors = build_pending(force=force, limit=limit)
        self.stdout.write(self.style.SUCCESS(f"Fingerprints: {ok} ok, {errors} errores"))
