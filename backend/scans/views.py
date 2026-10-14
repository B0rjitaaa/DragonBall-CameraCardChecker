from django.db import transaction
from django.http import HttpResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from . import camera
from .models import Scan
from .serializers import ConfirmScanSerializer, ScanSerializer
from .services import learn_from_scan
from .tasks import identify_card


class ScanViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """POST con `image` identifica una imagen subida; sin ella, captura de la cámara."""

    queryset = Scan.objects.select_related("matched_card")
    serializer_class = ScanSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ["status", "needs_review", "source"]

    def perform_create(self, serializer):
        has_image = bool(serializer.validated_data.get("image"))
        scan = serializer.save(source=Scan.Source.UPLOAD if has_image else Scan.Source.CAMERA)
        transaction.on_commit(lambda: identify_card.delay(scan.pk))

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.status_code = status.HTTP_202_ACCEPTED
        return response

    @action(detail=True, methods=["post"], parser_classes=[JSONParser])
    def confirm(self, request, pk=None):
        """Confirma o corrige la carta del escaneo y aprende de la foto.

        El recorte pasa a ser un fingerprint más de la carta elegida, así que
        la próxima vez esa carta se reconoce aunque su impresión no esté en el
        catálogo de Bandai (promos, premios de torneo…).
        """
        scan = self.get_object()
        if scan.status != Scan.Status.DONE or not scan.cropped_image:
            return Response(
                {"detail": "El escaneo no tiene recorte que confirmar"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ConfirmScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        card = serializer.validated_data["card"]

        with transaction.atomic():
            learn_from_scan(scan, card)
            scan.matched_card = card
            scan.confirmed = True
            scan.needs_review = False
            scan.save(update_fields=["matched_card", "confirmed", "needs_review"])
        return Response(self.get_serializer(scan).data)


@api_view(["GET"])
def camera_preview(_request):
    try:
        frame = camera.get_preview()
    except camera.CameraUnavailable as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    response = HttpResponse(frame, content_type="image/jpeg")
    response["Cache-Control"] = "no-store"
    return response
