from django.db import models

from cards.models import Card


class CollectionEntry(models.Model):
    class Condition(models.TextChoices):
        MINT = "mint", "Mint"
        NEAR_MINT = "near_mint", "Near Mint"
        EXCELLENT = "excellent", "Excellent"
        GOOD = "good", "Good"
        PLAYED = "played", "Played"
        POOR = "poor", "Poor"

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="collection_entries")
    quantity = models.PositiveIntegerField(default=1)
    condition = models.CharField(
        max_length=12, choices=Condition.choices, default=Condition.NEAR_MINT
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["card__card_number"]
        verbose_name_plural = "collection entries"
        constraints = [
            models.UniqueConstraint(fields=["card", "condition"], name="unique_card_condition"),
        ]

    def __str__(self):
        return f"{self.quantity}x {self.card} ({self.condition})"
