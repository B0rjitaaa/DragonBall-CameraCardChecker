"""Cliente del servicio `camera`, que es el único que abre /dev/video0."""

import requests
from django.conf import settings


class CameraUnavailable(Exception):
    pass


def _get(path: str, timeout: float) -> bytes:
    if not settings.CAMERA_URL:
        raise CameraUnavailable("CAMERA_URL no está configurado")
    try:
        response = requests.get(f"{settings.CAMERA_URL}{path}", timeout=timeout)
    except requests.RequestException as exc:
        raise CameraUnavailable(f"No se pudo contactar con el servicio de cámara: {exc}") from exc
    if response.status_code == 503:
        raise CameraUnavailable(
            "La cámara no está disponible: no llegan imágenes (¿webcam desconectada?)"
        )
    if not response.ok:
        raise CameraUnavailable(f"Error del servicio de cámara: HTTP {response.status_code}")
    return response.content


def get_frame(timeout: float = 6.0) -> bytes:
    """Frame reciente a resolución completa, para identificar."""
    return _get("/frame.jpg", timeout)


def get_preview(timeout: float = 5.0) -> bytes:
    """Frame reducido para la vista previa de la UI."""
    return _get("/preview.jpg", timeout)
