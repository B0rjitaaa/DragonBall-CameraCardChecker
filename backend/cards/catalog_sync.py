"""Sincronización del catálogo desde DragonBall-EnhancedAPI.

EnhancedAPI ya sincroniza a diario con Bandai TCG+ (con su gestión de bloqueos
403/429) y guarda el registro original de cada carta. Aquí se piden solo los
registros nuevos o cambiados (GET /api/cards/export/?updated_since=…), se
importan con el mismo importador que cartas_dbs.json y se calculan los
fingerprints de lo nuevo (descargando sus imágenes).
"""

import logging

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .fingerprints import build_pending
from .importer import upsert_cards
from .models import CatalogSync

logger = logging.getLogger(__name__)

_TIMEOUT = 120  # la exportación completa son ~8.000 registros (~20 MB)


def fetch_export(since=None) -> dict:
    base = settings.ENHANCED_API_URL.rstrip("/")
    if not base:
        raise RuntimeError("ENHANCED_API_URL no está configurado")
    params = {"updated_since": since.isoformat()} if since else {}
    response = requests.get(f"{base}/api/cards/export/", params=params, timeout=_TIMEOUT)
    response.raise_for_status()
    return response.json()


def run_sync(full: bool = False) -> CatalogSync:
    last = CatalogSync.objects.filter(status=CatalogSync.Status.SUCCESS, cursor__isnull=False).first()
    since = None if full or last is None else last.cursor
    sync = CatalogSync.objects.create(full=since is None)
    try:
        export = fetch_export(since)
        records = export["results"]
        stats = upsert_cards(records)
        sync.fetched = len(records)
        sync.created, sync.updated = stats.created, stats.updated
        if stats.created or stats.updated or sync.full:
            # Solo calcula lo que falta: cartas nuevas o con imagen cambiada.
            sync.fingerprints, sync.fingerprint_errors = build_pending()
        sync.cursor = parse_datetime(export["generated_at"])
        sync.status = CatalogSync.Status.SUCCESS
    except Exception as exc:  # noqa: BLE001 - el error queda en el histórico
        logger.exception("Sincronización del catálogo fallida")
        sync.status = CatalogSync.Status.FAILED
        sync.error = str(exc)
    sync.finished_at = timezone.now()
    sync.save()
    logger.info(
        "Catálogo: %s | %s registros, %s nuevas, %s cambiadas, %s fingerprints",
        sync.status, sync.fetched, sync.created, sync.updated, sync.fingerprints,
    )
    return sync
