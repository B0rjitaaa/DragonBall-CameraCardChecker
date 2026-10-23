from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from cards.models import Card

from .models import CollectionEntry, Location
from .serializers import (
    AdjustSerializer,
    CollectionEntrySerializer,
    LocationSerializer,
    MoveSerializer,
    NoteSerializer,
    ReorderSerializer,
)
from .services import (
    AmbiguousLocation,
    add_copies,
    card_summary,
    delete_location,
    move_copies,
    remove_copies,
    reorder_location,
)


class LocationViewSet(viewsets.ModelViewSet):
    """Ubicaciones (mazos, archivadores, almacén…) con sus totales."""

    serializer_class = LocationSerializer
    pagination_class = None

    def get_queryset(self):
        Location.default()  # "Sin ubicar" siempre existe
        # Meta.ordering no se aplica a consultas agregadas: hay que repetirlo.
        return LocationSerializer.annotate(Location.objects.all()).order_by(*Location._meta.ordering)

    def destroy(self, request, *args, **kwargs):
        """Sus copias vuelven a "Sin ubicar"."""
        try:
            delete_location(self.get_object())
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CollectionEntryViewSet(viewsets.ModelViewSet):
    queryset = CollectionEntry.objects.select_related("card", "location")
    serializer_class = CollectionEntrySerializer
    filterset_fields = ["location", "fake", "card__set_code", "card__color", "card__rarity"]
    search_fields = ["card__name", "card__card_number", "notes"]

    def create(self, request, *args, **kwargs):
        """Si la carta ya está en esa ubicación, suma la cantidad."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        existed = CollectionEntry.objects.filter(
            card=data["card"], location=data.get("location") or Location.default()
        ).exists()
        entry = add_copies(
            data["card"], data.get("location") or Location.default(), data.get("quantity", 1), data.get("notes", "")
        )
        return Response(
            self.get_serializer(entry).data,
            status=status.HTTP_200_OK if existed else status.HTTP_201_CREATED,
        )

    @action(detail=False)
    def export(self, request):
        """Colección completa en formato compacto, sin paginar (una fila por carta y ubicación).

        La consume DragonBall-EnhancedAPI ("Mi colección"), que la cruza con su
        catálogo por el id de Bandai (la clave común de los dos proyectos).
        """
        rows = self.get_queryset().order_by(
            "card__card_number", "-location__is_default", "location__position", "location__name", "fake"
        )
        return Response(
            [
                {
                    "bandai_id": e.card.bandai_id,
                    "card_number": e.card.card_number,
                    "name": e.card.name,
                    "quantity": e.quantity,
                    "location_id": e.location_id,
                    "location": e.location.name,
                    "location_kind": e.location.kind,
                    "fake": e.fake,
                    "position": e.position,
                    "notes": e.notes,
                }
                for e in rows
            ]
        )

    @action(detail=False, methods=["post"])
    def adjust(self, request):
        """Suma o resta copias de una carta: {bandai_id, delta, location?}.

        Lo usa "Mi colección" de DragonBall-EnhancedAPI (botones − / +). Al
        sumar, las copias entran en `location` ("Sin ubicar" por defecto). Al
        restar sin `location`, se quitan de "Sin ubicar" y, si no llega, de la
        única otra ubicación con copias; si hay varias, 409 con el reparto.
        """
        body = AdjustSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        card = get_object_or_404(Card, bandai_id=data["bandai_id"])
        if data["delta"] > 0:
            add_copies(card, data.get("location") or Location.default(), data["delta"])
        else:
            try:
                remove_copies(card, -data["delta"], data.get("location"), data.get("fake"))
            except AmbiguousLocation as exc:
                return Response({"detail": str(exc), **card_summary(card)}, status=status.HTTP_409_CONFLICT)
        return Response(card_summary(card))

    @action(detail=False, methods=["post"])
    def move(self, request):
        """Mueve copias entre ubicaciones: {bandai_id, source, target, quantity, source_fake?, target_fake?}.

        Con source == target y target_fake distinto de source_fake marca copias
        como falsas (o como auténticas).
        """
        body = MoveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        card = get_object_or_404(Card, bandai_id=data["bandai_id"])
        try:
            move_copies(
                card,
                data["source"],
                data["target"],
                data["quantity"],
                data["source_fake"],
                data["target_fake"],
                data.get("note_line") or None,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(card_summary(card))

    @action(detail=False, methods=["post"])
    def note(self, request):
        """Nota de las copias de una carta en una ubicación (p. ej. "página 12")."""
        body = NoteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        card = get_object_or_404(Card, bandai_id=data["bandai_id"])
        updated = CollectionEntry.objects.filter(card=card, location=data["location"], fake=data["fake"]).update(
            notes=data["notes"]
        )
        if not updated:
            return Response({"detail": "No hay copias de esa carta en esa ubicación"}, status=status.HTTP_404_NOT_FOUND)
        return Response(card_summary(card))

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        """Orden de las cartas en una ubicación: {location, bandai_ids: [en el orden deseado]}."""
        body = ReorderSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        reorder_location(body.validated_data["location"], body.validated_data["bandai_ids"])
        return Response(status=status.HTTP_204_NO_CONTENT)
