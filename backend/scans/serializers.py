from django.conf import settings
from rest_framework import serializers

from cards.models import Card
from cards.serializers import CardSerializer

from .models import Scan, ScanSession


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
            "session",
            "added_to_collection",
            "dismissed",
            "method",
            "candidates",
            "error",
            "duration_ms",
            "created_at",
            "finished_at",
        ]
        read_only_fields = [f for f in fields if f not in ("image", "session")]
        extra_kwargs = {"image": {"required": False}, "session": {"required": False}}


class ConfirmScanSerializer(serializers.Serializer):
    card_id = serializers.PrimaryKeyRelatedField(queryset=Card.objects.all(), source="card")


class SessionScanSerializer(serializers.ModelSerializer):
    """Escaneo resumido para el panel de la sesión."""

    card_number = serializers.CharField(source="matched_card.card_number", default=None)
    card_name = serializers.CharField(source="matched_card.name", default=None)

    class Meta:
        model = Scan
        fields = [
            "id",
            "status",
            "cropped_image",
            "card_detected",
            "card_number",
            "card_name",
            "confidence",
            "needs_review",
            "confirmed",
            "added_to_collection",
            "dismissed",
            "error",
            "duration_ms",
            "created_at",
        ]


class ScanSessionSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()
    scans = serializers.SerializerMethodField()

    auto_add_min_confidence = serializers.SerializerMethodField()

    class Meta:
        model = ScanSession
        fields = ["id", "started_at", "ended_at", "condition", "auto_add_min_confidence", "stats", "scans"]
        read_only_fields = ["started_at", "ended_at", "condition"]

    def get_auto_add_min_confidence(self, _obj):
        return settings.AUTO_ADD_MIN_CONFIDENCE

    def _visible(self, obj):
        # Los disparos sin carta (zona vacía) no se muestran.
        return obj.scans.exclude(dismissed=True, card_detected=False).order_by("-created_at")

    def get_stats(self, obj):
        scans = list(self._visible(obj))
        done = [s for s in scans if s.status == Scan.Status.DONE and not s.dismissed]
        return {
            "total": len(scans),
            "added": sum(s.added_to_collection for s in done),
            "review": sum(not s.added_to_collection for s in done),
            "pending": sum(s.status in (Scan.Status.PENDING, Scan.Status.PROCESSING) for s in scans),
            "failed": sum(s.status == Scan.Status.FAILED for s in scans),
            "undone": sum(s.dismissed for s in scans),
        }

    def get_scans(self, obj):
        return SessionScanSerializer(
            self._visible(obj).select_related("matched_card")[:200], many=True, context=self.context
        ).data
