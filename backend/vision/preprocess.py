"""Detección de la carta en la foto, recorte y corrección de perspectiva."""

import cv2
import numpy as np

# Proporción física 63 x 88 mm. Tanto las imágenes oficiales como las
# capturas se normalizan a este tamaño antes de calcular fingerprints.
CARD_W, CARD_H = 315, 440

_DETECT_MAX_SIDE = 800
_MIN_AREA_RATIO = 0.08


def decode_image(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("No se pudo decodificar la imagen")
    return img


def encode_jpeg(img: np.ndarray, quality: int = 90) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("No se pudo codificar la imagen")
    return buf.tobytes()


def order_points(pts: np.ndarray) -> np.ndarray:
    """Ordena 4 puntos como arriba-izq, arriba-der, abajo-der, abajo-izq."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )


def find_card_quad(img: np.ndarray) -> np.ndarray | None:
    """Devuelve las 4 esquinas de la carta (coordenadas de `img`) o None."""
    h, w = img.shape[:2]
    scale = min(1.0, _DETECT_MAX_SIDE / max(h, w))
    small = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    min_area = _MIN_AREA_RATIO * small.shape[0] * small.shape[1]

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 40, 140)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

    for contour in contours:
        if cv2.contourArea(contour) < min_area:
            break
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return approx.reshape(4, 2).astype(np.float32) / scale

    # Esquinas redondeadas o bordes parcialmente ocultos: rectángulo mínimo.
    if contours and cv2.contourArea(contours[0]) >= min_area:
        box = cv2.boxPoints(cv2.minAreaRect(contours[0]))
        return box.astype(np.float32) / scale
    return None


def warp_card(img: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """Endereza la carta a CARD_W x CARD_H, girándola a vertical si hace falta."""
    tl, tr, br, bl = order_points(quad)
    width = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl))
    height = max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    src = np.array([tl, tr, br, bl], dtype=np.float32)
    if width > height:
        # Carta apaisada en la foto: rotamos el origen 90º para dejarla vertical.
        src = np.array([bl, tl, tr, br], dtype=np.float32)
    dst = np.array(
        [[0, 0], [CARD_W - 1, 0], [CARD_W - 1, CARD_H - 1], [0, CARD_H - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, matrix, (CARD_W, CARD_H))


def normalize_reference(img: np.ndarray) -> np.ndarray:
    """Lleva una imagen oficial (ya recortada) al tamaño canónico vertical."""
    h, w = img.shape[:2]
    if w > h:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    return cv2.resize(img, (CARD_W, CARD_H), interpolation=cv2.INTER_AREA)


def extract_card(img: np.ndarray) -> tuple[np.ndarray, bool]:
    """Recorta la carta de una captura. Devuelve (recorte, carta_detectada)."""
    quad = find_card_quad(img)
    if quad is None:
        return normalize_reference(img), False
    return warp_card(img, quad), True
