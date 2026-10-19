from celery import shared_task

from .catalog_sync import run_sync
from .fingerprints import build_pending


@shared_task
def sync_catalog(full: bool = False):
    """Trae del catálogo de EnhancedAPI las cartas nuevas o cambiadas."""
    sync = run_sync(full=full)
    return {"status": sync.status, "created": sync.created, "updated": sync.updated, "error": sync.error}


@shared_task
def build_fingerprints(force: bool = False):
    ok, errors = build_pending(force=force)
    return {"ok": ok, "errors": errors}
