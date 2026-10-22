from django.conf import settings
from rest_framework import serializers

from cards.models import Card
from cards.serializers import CardSerializer
from collection.models import DEFAULT_LOCATION_NAME

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
            "copies",
            "dismissed",
            "after_empty",
            "repeat_suspect",
            "binder_page",
            "binder_slot",
            "method",
            "candidates",
            "error",
            "duration_ms",
            "created_at",
            "finished_at",
        ]
        read_only_fields = [
            f for f in fields if f not in ("image", "session", "after_empty", "binder_page", "binder_slot")
        ]
        extra_kwargs = {
            "image": {"required": False},
            "session": {"required": False},
            "after_empty": {"required": False},
            "binder_page": {"required": False, "min_value": 1, "max_value": 999},
            "binder_slot": {"required": False, "min_value": 1, "max_value": 9},
        }


class ConfirmScanSerializer(serializers.Serializer):
    card_id = serializers.PrimaryKeyRelatedField(queryset=Card.objects.all(), source="card")
    # Modo ráfaga: cuántas copias añadir (por defecto, las que ya tenga el escaneo).
    copies = serializers.IntegerField(min_value=1, max_value=99, required=False)


class ScanCopiesSerializer(serializers.Serializer):
    copies = serializers.IntegerField(min_value=1, max_value=99)


class SessionScanSerializer(serializers.ModelSerializer):
    """Escaneo resumido para el panel de la sesión."""

    card_id = serializers.IntegerField(source="matched_card_id", default=None)
    card_number = serializers.CharField(source="matched_card.card_number", default=None)
    card_name = serializers.CharField(source="matched_card.name", default=None)

    class Meta:
        model = Scan
        fields = [
            "id",
            "status",
            "cropped_image",
            "card_detected",
            "card_id",
            "card_number",
            "card_name",
            "confidence",
            "needs_review",
            "confirmed",
            "added_to_collection",
            "copies",
            "dismissed",
            "repeat_suspect",
            "binder_page",
            "binder_slot",
            "error",
            "duration_ms",
            "created_at",
        ]


class ScanSessionSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()
    scans = serializers.SerializerMethodField()

    auto_add_min_confidence = serializers.SerializerMethodField()
    location_name = serializers.SerializerMethodField()

    def get_location_name(self, obj):
        return obj.location.name if obj.location_id else DEFAULT_LOCATION_NAME

    class Meta:
        model = ScanSession
        fields = [
            "id", "started_at", "ended_at", "mode", "location", "location_name", "auto_add_min_confidence", "stats",
            "scans",
        ]
        read_only_fields = ["started_at", "ended_at"]

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
            "copies": sum(s.copies for s in done if s.added_to_collection),
            "review": sum(not s.added_to_collection for s in done),
            "pending": sum(s.status in (Scan.Status.PENDING, Scan.Status.PROCESSING) for s in scans),
            "failed": sum(s.status == Scan.Status.FAILED for s in scans),
            "undone": sum(s.dismissed for s in scans),
        }

    def get_scans(self, obj):
        return SessionScanSerializer(
            self._visible(obj).select_related("matched_card")[:200], many=True, context=self.context
        ).data
