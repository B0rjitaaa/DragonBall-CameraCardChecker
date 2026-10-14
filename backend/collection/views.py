from django.db import transaction
from django.db.models import F
from rest_framework import status, viewsets
from rest_framework.response import Response

from .models import CollectionEntry
from .serializers import CollectionEntrySerializer


class CollectionEntryViewSet(viewsets.ModelViewSet):
    queryset = CollectionEntry.objects.select_related("card")
    serializer_class = CollectionEntrySerializer
    filterset_fields = ["condition", "card__set_code", "card__color", "card__rarity"]
    search_fields = ["card__name", "card__card_number", "notes"]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Si la carta ya está con esa condición, suma la cantidad."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        entry, created = CollectionEntry.objects.select_for_update().get_or_create(
            card=data["card"],
            condition=data.get("condition", CollectionEntry.Condition.NEAR_MINT),
            defaults={"quantity": data.get("quantity", 1), "notes": data.get("notes", "")},
        )
        if not created:
            CollectionEntry.objects.filter(pk=entry.pk).update(
                quantity=F("quantity") + data.get("quantity", 1)
            )
            entry.refresh_from_db()
        return Response(
            self.get_serializer(entry).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
