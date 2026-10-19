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


class AdjustSerializer(serializers.Serializer):
    """Sumar o restar copias de una carta (por id de Bandai)."""

    bandai_id = serializers.IntegerField()
    delta = serializers.IntegerField(min_value=-10, max_value=10)
    # Al sumar, estado de las copias nuevas; al restar, de qué estado quitarlas.
    condition = serializers.ChoiceField(choices=CollectionEntry.Condition.choices, required=False)

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("delta no puede ser 0")
        return value
