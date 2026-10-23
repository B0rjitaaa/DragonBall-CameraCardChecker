"""Operaciones sobre la colección: sumar, quitar y mover copias entre ubicaciones."""

from django.db import transaction
from django.db.models import F

from cards.models import Card

from .models import CollectionEntry, Location


class AmbiguousLocation(Exception):
    """Hay que quitar copias y están repartidas: hay que decir de qué ubicación."""

    def __init__(self, card: Card):
        super().__init__("Las copias están en varias ubicaciones: indica de cuál quitarla")
        self.card = card


def card_summary(card: Card) -> dict:
    """Total de copias de una carta y su reparto por ubicación (una fila por ubicación y autenticidad)."""
    entries = CollectionEntry.objects.filter(card=card).select_related("location").order_by(
        "-location__is_default", "location__position", "location__name", "fake"
    )
    locations = [
        {
            "id": e.location_id,
            "name": e.location.name,
            "kind": e.location.kind,
            "quantity": e.quantity,
            "fake": e.fake,
            "notes": e.notes,
        }
        for e in entries
    ]
    return {
        "bandai_id": card.bandai_id,
        "quantity": sum(loc["quantity"] for loc in locations),
        "fakes": sum(loc["quantity"] for loc in locations if loc["fake"]),
        "locations": locations,
    }


def add_copies(card: Card, location: Location, quantity: int, notes: str = "", fake: bool = False) -> CollectionEntry:
    with transaction.atomic():
        entry, created = CollectionEntry.objects.select_for_update().get_or_create(
            card=card, location=location, fake=fake, defaults={"quantity": quantity, "notes": notes}
        )
        if not created:
            CollectionEntry.objects.filter(pk=entry.pk).update(quantity=F("quantity") + quantity)
            if notes and notes not in entry.notes:
                entry.notes = f"{entry.notes}\n{notes}".strip()
                entry.save(update_fields=["notes"])
            entry.refresh_from_db()
    return entry


def _take(entry: CollectionEntry, quantity: int) -> None:
    if quantity >= entry.quantity:
        entry.delete()
    else:
        CollectionEntry.objects.filter(pk=entry.pk).update(quantity=F("quantity") - quantity)


def remove_copies(card: Card, quantity: int, location: Location | None = None, fake: bool | None = None) -> None:
    """Quita copias. Sin ubicación: primero de "Sin ubicar" y, si no llega,
    de la única otra ubicación que tenga copias (si hay varias, AmbiguousLocation).
    Con `fake` solo las auténticas (False) o las falsas (True); sin él, primero
    las auténticas."""
    with transaction.atomic():
        entries = list(
            CollectionEntry.objects.select_for_update().filter(card=card).select_related("location").order_by("fake")
        )
        if fake is not None:
            entries = [e for e in entries if e.fake == fake]
        if location is not None:
            entries = [e for e in entries if e.location_id == location.pk]
        else:
            default = [e for e in entries if e.location.is_default]
            others = [e for e in entries if not e.location.is_default]
            missing = quantity - sum(e.quantity for e in default)
            if missing > 0 and len({e.location_id for e in others}) > 1:
                raise AmbiguousLocation(card)
            entries = default + others
        remaining = quantity
        for entry in entries:
            if remaining <= 0:
                break
            take = min(entry.quantity, remaining)
            _take(entry, take)
            remaining -= take


def move_copies(
    card: Card,
    source: Location,
    target: Location,
    quantity: int,
    source_fake: bool = False,
    target_fake: bool | None = None,
) -> None:
    """Pasa copias de una ubicación a otra, o las marca como falsas / auténticas
    (misma ubicación, `target_fake` distinto). El total no cambia."""
    target_fake = source_fake if target_fake is None else target_fake
    if source.pk == target.pk and source_fake == target_fake:
        return
    with transaction.atomic():
        entry = CollectionEntry.objects.select_for_update().filter(card=card, location=source, fake=source_fake).first()
        if entry is None or entry.quantity < quantity:
            available = entry.quantity if entry else 0
            kind = " falsas" if source_fake else ""
            raise ValueError(f"En «{source.name}» solo hay {available} copias{kind}")
        notes = entry.notes
        _take(entry, quantity)
        add_copies(card, target, quantity, notes if quantity == entry.quantity else "", fake=target_fake)


def delete_location(location: Location) -> None:
    """Borra una ubicación; sus copias vuelven a "Sin ubicar"."""
    from scans.models import Scan

    if location.is_default:
        raise ValueError("«Sin ubicar» no se puede borrar")
    default = Location.default()
    with transaction.atomic():
        for entry in list(CollectionEntry.objects.select_for_update().filter(location=location)):
            kept = add_copies(entry.card, default, entry.quantity, entry.notes, fake=entry.fake)
            Scan.objects.filter(collection_entry=entry).update(collection_entry=kept)
            entry.delete()
        location.delete()
