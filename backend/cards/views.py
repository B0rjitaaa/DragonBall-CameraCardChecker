from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Card
from .serializers import CardSerializer

FACET_FIELDS = ("set_code", "rarity", "card_type", "color")


class CardViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Card.objects.all()
    serializer_class = CardSerializer
    filterset_fields = FACET_FIELDS
    search_fields = ["name", "card_number", "text", "back_name"]
    ordering_fields = ["card_number", "name", "set_code"]

    @action(detail=False)
    def facets(self, request):
        """Valores distintos de cada faceta para construir los filtros de la UI."""
        qs = self.filter_queryset(self.get_queryset())
        return Response(
            {
                # order_by(field): sin él, la ordenación del modelo rompe el distinct().
                field: [v for v in qs.order_by(field).values_list(field, flat=True).distinct() if v]
                for field in FACET_FIELDS
            }
        )
