import logging
import time
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from vision.preprocess import decode_image, encode_jpeg

from . import camera
from .models import Scan
from .services import run_identification, serialize_candidates

logger = logging.getLogger(__name__)


@shared_task
def identify_card(scan_id: int):
    scan = Scan.objects.get(pk=scan_id)
    scan.status = Scan.Status.PROCESSING
    scan.save(update_fields=["status"])
    started = time.monotonic()

    try:
        if scan.image:
            with scan.image.open("rb") as fh:
                data = fh.read()
        else:
            data = camera.get_frame()
            scan.image.save(f"scan_{scan.pk}.jpg", ContentFile(data), save=False)

        result = run_identification(decode_image(data))

        scan.cropped_image.save(
            f"scan_{scan.pk}_crop.jpg", ContentFile(encode_jpeg(result.crop)), save=False
        )
        scan.card_detected = result.card_detected
        scan.method = result.method
        scan.candidates = serialize_candidates(result)
        scan.confidence = round(result.confidence, 3) if result.best else None
        scan.matched_card_id = result.best.card_id if result.best else None
        scan.needs_review = result.confidence < settings.MATCH_MIN_CONFIDENCE
        scan.status = Scan.Status.DONE
    except Exception as exc:  # noqa: BLE001 - el error se guarda en el Scan
        logger.exception("Scan %s falló", scan_id)
        scan.status = Scan.Status.FAILED
        scan.error = str(exc)

    scan.duration_ms = int((time.monotonic() - started) * 1000)
    scan.finished_at = timezone.now()
    scan.save()
    return scan.status


@shared_task
def cleanup_old_scans():
    """Borra las imágenes de escaneos antiguos (el registro se conserva)."""
    cutoff = timezone.now() - timedelta(days=settings.SCAN_RETENTION_DAYS)
    removed = 0
    for scan in Scan.objects.filter(created_at__lt=cutoff).exclude(image=""):
        for field in (scan.image, scan.cropped_image):
            if field:
                field.delete(save=False)
        scan.save(update_fields=["image", "cropped_image"])
        removed += 1
    return removed
