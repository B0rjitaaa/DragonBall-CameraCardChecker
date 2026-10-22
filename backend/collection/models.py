from django.db import models

from cards.models import Card

DEFAULT_LOCATION_NAME = "Sin ubicar"


class Location(models.Model):
    """Dónde están guardadas las copias: un mazo, un archivador, una caja…"""

    class Kind(models.TextChoices):
        DECK = "deck", "Mazo"
        BINDER = "binder", "Archivador"
        STORAGE = "storage", "Almacén"
        OTHER = "other", "Otro"

    name = models.CharField(max_length=80, unique=True)
    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.OTHER)
    notes = models.TextField(blank=True)
    # "Sin ubicar": destino por defecto de lo escaneado y de lo que queda al
    # borrar una ubicación. Siempre existe y no se puede borrar.
    is_default = models.BooleanField(default=False)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "position", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"], condition=models.Q(is_default=True), name="single_default_location"
            ),
        ]

    def __str__(self):
        return self.name

    @classmethod
    def default(cls) -> "Location":
        location, _ = cls.objects.get_or_create(
            is_default=True, defaults={"name": DEFAULT_LOCATION_NAME, "kind": cls.Kind.OTHER}
        )
        return location


class CollectionEntry(models.Model):
    """Copias de una carta en una ubicación."""

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="collection_entries")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="entries")
    quantity = models.PositiveIntegerField(default=1)
    # Detalle dentro de la ubicación (p. ej. "página 12").
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["card__card_number", "location"]
        verbose_name_plural = "collection entries"
        constraints = [
            models.UniqueConstraint(fields=["card", "location"], name="unique_card_location"),
        ]

    def __str__(self):
        return f"{self.quantity}x {self.card} ({self.location})"
