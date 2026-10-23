from django.db.models import Count, Q, Sum
from rest_framework import serializers

from cards.models import Card
from cards.serializers import CardSummarySerializer

from .models import CollectionEntry, Location


class LocationSerializer(serializers.ModelSerializer):
    cards = serializers.IntegerField(read_only=True, default=0)
    copies = serializers.IntegerField(read_only=True, default=0)
    fakes = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Location
        fields = ["id", "name", "kind", "notes", "is_default", "position", "cards", "copies", "fakes"]
        read_only_fields = ["is_default"]

    @staticmethod
    def annotate(queryset):
        return queryset.annotate(
            cards=Count("entries__card", distinct=True),
            copies=Sum("entries__quantity", default=0),
            fakes=Sum("entries__quantity", filter=Q(entries__fake=True), default=0),
        )


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
            "id", "card", "card_id", "location", "location_name", "quantity", "fake", "notes", "created_at", "updated_at",
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
    # Al restar: solo de las auténticas (False) o de las falsas (True). Al sumar se ignora:
    # las copias nuevas son auténticas; para marcar falsas se usa move con target_fake.
    fake = serializers.BooleanField(required=False, allow_null=True, default=None)

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("delta no puede ser 0")
        return value


class MoveSerializer(serializers.Serializer):
    bandai_id = serializers.IntegerField()
    source = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    target = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    quantity = serializers.IntegerField(min_value=1, max_value=999)
    # Copias de origen falsas o auténticas; destino: igual que el origen salvo que se diga
    # (misma ubicación y target_fake distinto = marcar como falsas / auténticas).
    source_fake = serializers.BooleanField(required=False, default=False)
    target_fake = serializers.BooleanField(required=False, allow_null=True, default=None)
    # Línea de la nota (p. ej. la posición en el archivador) que se va con las copias.
    note_line = serializers.CharField(required=False, allow_blank=True, max_length=200)


class NoteSerializer(serializers.Serializer):
    bandai_id = serializers.IntegerField()
    location = serializers.PrimaryKeyRelatedField(queryset=Location.objects.all())
    fake = serializers.BooleanField(required=False, default=False)
    notes = serializers.CharField(allow_blank=True, max_length=500)
