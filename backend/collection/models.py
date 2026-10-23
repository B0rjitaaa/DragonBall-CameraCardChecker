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
    """Copias de una carta en una ubicación (las falsas, en su propia fila)."""

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="collection_entries")
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name="entries")
    quantity = models.PositiveIntegerField(default=1)
    # Copias falsificadas (p. ej. de AliExpress). Las marca el usuario a mano.
    fake = models.BooleanField(default=False, db_index=True)
    # Orden de la carta dentro de su ubicación ("Mi orden", arrastrando en Mi colección).
    # Las filas auténtica y falsa de una carta en una ubicación comparten posición.
    position = models.PositiveIntegerField(default=0)
    # Detalle dentro de la ubicación (p. ej. "página 12").
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["card__card_number", "location", "fake"]
        verbose_name_plural = "collection entries"
        constraints = [
            models.UniqueConstraint(fields=["card", "location", "fake"], name="unique_card_location_fake"),
        ]

    def __str__(self):
        return f"{self.quantity}x {self.card} ({self.location}{', falsa' if self.fake else ''})"

    def save(self, *args, **kwargs):
        if self._state.adding and not self.position:
            # Una carta nueva en la ubicación va al final; si ya estaba (la otra fila,
            # auténtica o falsa), en su mismo sitio.
            siblings = CollectionEntry.objects.filter(location_id=self.location_id)
            same = siblings.filter(card_id=self.card_id).values_list("position", flat=True).first()
            self.position = same or (siblings.aggregate(m=models.Max("position"))["m"] or 0) + 1
        super().save(*args, **kwargs)
