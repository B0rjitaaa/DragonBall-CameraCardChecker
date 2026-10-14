from django.core.management.base import BaseCommand

from cards import bandai
from cards.importer import upsert_cards
from cards.tasks import build_fingerprints


class Command(BaseCommand):
    help = "Sincroniza el catálogo con Bandai TCG+ y encola el cálculo de fingerprints."

    def handle(self, *args, **options):
        stats = upsert_cards(bandai.fetch_cards())
        self.stdout.write(self.style.SUCCESS(f"Sincronización terminada: {stats}"))
        build_fingerprints.delay()
        self.stdout.write("Cálculo de fingerprints encolado en el worker.")
