import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from .bandai import normalize_card
from .models import Card

logger = logging.getLogger(__name__)

_BATCH_SIZE = 500


@dataclass
class ImportStats:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0

    def __str__(self):
        return (
            f"creadas={self.created} actualizadas={self.updated} "
            f"sin cambios={self.unchanged} descartadas={self.skipped}"
        )


@transaction.atomic
def upsert_cards(records) -> ImportStats:
    """Crea o actualiza cartas (clave: bandai_id) a partir de registros de Bandai."""
    stats = ImportStats()
    now = timezone.now()
    existing = {c.bandai_id: c for c in Card.objects.all()}
    to_create: dict[int, Card] = {}
    to_update: dict[int, Card] = {}
    changed_fields: set[str] = set()

    for raw in records:
        data = normalize_card(raw)
        if data is None:
            stats.skipped += 1
            continue

        card = existing.get(data["bandai_id"])
        if card is None:
            to_create[data["bandai_id"]] = Card(**data)
            continue

        changed = [field for field, value in data.items() if getattr(card, field) != value]
        if changed:
            for field in changed:
                setattr(card, field, data[field])
            card.updated_at = now  # bulk_update no aplica auto_now
            changed_fields.update(changed)
            to_update[card.bandai_id] = card
        else:
            stats.unchanged += 1

    Card.objects.bulk_create(to_create.values(), batch_size=_BATCH_SIZE)
    if to_update:
        Card.objects.bulk_update(
            to_update.values(), [*changed_fields, "updated_at"], batch_size=_BATCH_SIZE
        )
    stats.created, stats.updated = len(to_create), len(to_update)

    logger.info("Importación de cartas: %s", stats)
    return stats
