from rest_framework import serializers

from cards.models import Card
from cards.serializers import CardSummarySerializer

from .models import CollectionEntry


class CollectionEntrySerializer(serializers.ModelSerializer):
    card = CardSummarySerializer(read_only=True)
    card_id = serializers.PrimaryKeyRelatedField(
        source="card", queryset=Card.objects.all(), write_only=True
    )

    class Meta:
        model = CollectionEntry
        fields = ["id", "card", "card_id", "quantity", "condition", "notes", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]
        # La unicidad (card, condition) se resuelve sumando cantidades en create().
        validators = []
