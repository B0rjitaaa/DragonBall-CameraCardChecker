from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from . import camera
from .models import Scan, ScanSession
from .serializers import ConfirmScanSerializer, ScanCopiesSerializer, ScanSerializer, ScanSessionSerializer
from .services import add_scan_to_collection, learn_from_scan, remove_scan_from_collection, set_scan_copies
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
    filterset_fields = ["status", "needs_review", "source", "session", "added_to_collection"]

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
            if scan.added_to_collection and scan.matched_card_id != card.id:
                # Corrección de una carta ya añadida: se cambia por la buena.
                remove_scan_from_collection(scan)
            scan.matched_card = card
            scan.confirmed = True
            scan.needs_review = False
            scan.dismissed = False
            scan.repeat_suspect = False  # confirmar = "sí, es otra copia"
            if scan.session_id and "copies" in serializer.validated_data:
                scan.copies = serializer.validated_data["copies"]
            scan.save(
                update_fields=["matched_card", "confirmed", "needs_review", "dismissed", "repeat_suspect", "copies"]
            )
            if scan.session_id:
                # En modo ráfaga, confirmar = añadir a la colección.
                add_scan_to_collection(scan)
        return Response(self.get_serializer(scan).data)

    @action(detail=True, methods=["post"], parser_classes=[JSONParser])
    def copies(self, request, pk=None):
        """Modo ráfaga: cuántas copias de la carta suma este escaneo a la colección."""
        scan = self.get_object()
        if not scan.session_id or not scan.added_to_collection:
            return Response(
                {"detail": "Solo se pueden cambiar las copias de una carta añadida en modo ráfaga"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ScanCopiesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_scan_copies(scan, serializer.validated_data["copies"])
        return Response(self.get_serializer(scan).data)

    @action(detail=True, methods=["post"])
    def undo(self, request, pk=None):
        """Deshace un escaneo de modo ráfaga: lo quita de la colección y lo descarta."""
        scan = self.get_object()
        with transaction.atomic():
            remove_scan_from_collection(scan)
            scan.dismissed = True
            scan.save(update_fields=["dismissed"])
        return Response(self.get_serializer(scan).data)


class ScanSessionViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Sesiones de modo ráfaga."""

    queryset = ScanSession.objects.all()
    serializer_class = ScanSessionSerializer

    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        session = self.get_object()
        if session.ended_at is None:
            session.ended_at = timezone.now()
            session.save(update_fields=["ended_at"])
        return Response(self.get_serializer(session).data)


@api_view(["GET"])
def camera_preview(_request):
    try:
        frame = camera.get_preview()
    except camera.CameraUnavailable as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    response = HttpResponse(frame, content_type="image/jpeg")
    response["Cache-Control"] = "no-store"
    return response
