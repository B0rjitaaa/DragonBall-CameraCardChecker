from celery import shared_task

from . import bandai
from .fingerprints import build_pending
from .importer import upsert_cards


@shared_task
def sync_bandai_catalog():
    stats = upsert_cards(bandai.fetch_cards())
    if stats.created or stats.updated:
        build_fingerprints.delay()
    return str(stats)


@shared_task
def build_fingerprints(force: bool = False):
    ok, errors = build_pending(force=force)
    return {"ok": ok, "errors": errors}
