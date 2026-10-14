from rest_framework import serializers

from cards.models import Card
from cards.serializers import CardSerializer

from .models import Scan


class ScanSerializer(serializers.ModelSerializer):
    matched_card = CardSerializer(read_only=True)

    class Meta:
        model = Scan
        fields = [
            "id",
            "source",
            "status",
            "image",
            "cropped_image",
            "card_detected",
            "matched_card",
            "confidence",
            "needs_review",
            "confirmed",
            "method",
            "candidates",
            "error",
            "duration_ms",
            "created_at",
            "finished_at",
        ]
        read_only_fields = [f for f in fields if f != "image"]
        extra_kwargs = {"image": {"required": False}}


class ConfirmScanSerializer(serializers.Serializer):
    card_id = serializers.PrimaryKeyRelatedField(queryset=Card.objects.all(), source="card")
