import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from cards.bandai import extract_items
from cards.importer import upsert_cards


class Command(BaseCommand):
    help = "Importa cartas desde un fichero JSON (lista o respuesta de la API de Bandai)."

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path)

    def handle(self, *args, path: Path, **options):
        if not path.exists():
            raise CommandError(f"No existe {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = extract_items(payload)
        if not records:
            raise CommandError("El fichero no contiene una lista de cartas reconocible")
        stats = upsert_cards(records)
        self.stdout.write(self.style.SUCCESS(f"Importación terminada: {stats}"))
        self.stdout.write("Siguiente paso: `download_card_images` y `build_fingerprints` (o `make catalog`).")
