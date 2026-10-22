from django.db.models import Count, Sum
from rest_framework import serializers

from cards.models import Card
from cards.serializers import CardSummarySerializer

from .models import CollectionEntry, Location


class LocationSerializer(serializers.ModelSerializer):
    cards = serializers.IntegerField(read_only=True, default=0)
    copies = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Location
        fields = ["id", "name", "kind", "notes", "is_default", "position", "cards", "copies"]
        read_only_fields = ["is_default"]

    @staticmethod
    def annotate(queryset):
        return queryset.annotate(cards=Count("entries"), copies=Sum("entries__quantity", default=0))


class CollectionEntrySerializer(serializers.ModelSerializer):
    card = CardSummarySerializer(read_only=True)
    card_id = serializers.PrimaryKeyRelatedField(
        source="card", queryset=Card.objects.all(), write_only=True
    )
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all(), required=False)
    location_name = serializers.CharField(source="location.name", read_only=True)

    class Meta:
        model = CollectionEntry
        fields = [
            "id", "card", "card_id", "location", "location_name", "quantity", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
        # La unicidad (card, location) se resuelve sumando cantidades en create().
        validators = []


class AdjustSerializer(serializers.Serializer):
    """Sumar o restar copias de una carta (por id de Bandai)."""

    bandai_id = serializers.IntegerField()
    delta = serializers.IntegerField(min_value=-10, max_value=10)
    # Al sumar, dónde entran (por defecto "Sin ubicar"); al restar, de dónde se quitan.
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all(), required=False)

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("delta no puede ser 0")
        return value


class MoveSerializer(serializers.Serializer):
    bandai_id = serializers.IntegerField()
    source = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    target = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    quantity = serializers.IntegerField(min_value=1, max_value=999)


class NoteSerializer(serializers.Serializer):
    bandai_id = serializers.IntegerField()
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    notes = serializers.CharField(allow_blank=True, max_length=500)
