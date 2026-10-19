from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import CollectionEntry
from cards.models import Card

from .serializers import AdjustSerializer, CollectionEntrySerializer


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

    @action(detail=False)
    def export(self, request):
        """Colección completa en formato compacto, sin paginar.

        La consume DragonBall-EnhancedAPI ("Mi colección"), que la cruza con su
        catálogo por el id de Bandai (la clave común de los dos proyectos).
        """
        rows = self.get_queryset().order_by("card__card_number", "condition").values_list(
            "card__bandai_id", "card__card_number", "card__name", "quantity", "condition"
        )
        return Response(
            [
                {
                    "bandai_id": bandai_id,
                    "card_number": number,
                    "name": name,
                    "quantity": quantity,
                    "condition": condition,
                }
                for bandai_id, number, name, quantity, condition in rows
            ]
        )

    @action(detail=False, methods=["post"])
    def adjust(self, request):
        """Suma o resta copias de una carta: {bandai_id, delta, condition?}.

        Lo usa "Mi colección" de DragonBall-EnhancedAPI (botones − / +). Al
        sumar, las copias entran en `condition` (Near Mint por defecto). Al
        restar, se quitan de `condition` si se indica; si no, primero de Near
        Mint y después del estado con más copias. Una entrada a 0 se borra.
        """
        body = AdjustSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        card = get_object_or_404(Card, bandai_id=data["bandai_id"])
        delta = data["delta"]

        with transaction.atomic():
            if delta > 0:
                condition = data.get("condition", CollectionEntry.Condition.NEAR_MINT)
                entry, created = CollectionEntry.objects.select_for_update().get_or_create(
                    card=card, condition=condition, defaults={"quantity": delta}
                )
                if not created:
                    CollectionEntry.objects.filter(pk=entry.pk).update(quantity=F("quantity") + delta)
            else:
                entries = list(CollectionEntry.objects.select_for_update().filter(card=card))
                if "condition" in data:
                    entries = [e for e in entries if e.condition == data["condition"]]
                entries.sort(
                    key=lambda e: (e.condition != CollectionEntry.Condition.NEAR_MINT, -e.quantity)
                )
                remaining = -delta
                for entry in entries:
                    if remaining == 0:
                        break
                    take = min(entry.quantity, remaining)
                    remaining -= take
                    if take == entry.quantity:
                        entry.delete()
                    else:
                        CollectionEntry.objects.filter(pk=entry.pk).update(quantity=F("quantity") - take)

        conditions = dict(
            CollectionEntry.objects.filter(card=card).values_list("condition", "quantity")
        )
        return Response(
            {"bandai_id": card.bandai_id, "quantity": sum(conditions.values()), "conditions": conditions}
        )
