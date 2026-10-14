from django.core.management.base import BaseCommand

from cards.images import download_missing
from cards.models import Card


class Command(BaseCommand):
    help = "Descarga a CARD_IMAGES_DIR las imágenes oficiales (anverso y reverso) que falten."

    def add_arguments(self, parser):
        parser.add_argument("--workers", type=int, default=8)

    def handle(self, *args, workers: int, **options):
        urls = []
        for front, back in Card.objects.values_list("image_url", "image_back_url"):
            urls += [front, back]

        def progress(done, total, errors):
            self.stdout.write(f"  {done}/{total} ({errors} errores)")

        ok, cached, errors = download_missing(urls, workers=workers, progress=progress)
        self.stdout.write(
            self.style.SUCCESS(f"Imágenes: {ok} descargadas, {cached} ya en caché, {errors} errores")
        )
