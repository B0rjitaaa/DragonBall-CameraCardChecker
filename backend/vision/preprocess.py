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


def decode_reference(data: bytes) -> np.ndarray:
    """Decodifica una imagen oficial quitando los márgenes transparentes.

    Las cartas apaisadas (Z-Extra…) vienen en un lienzo vertical con la carta
    en el centro y franjas transparentes arriba y abajo: sin recortarlas, la
    referencia sería una carta aplastada con bandas que ninguna foto se parece.
    """
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("No se pudo decodificar la imagen")
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        ys, xs = np.nonzero(img[..., 3] > 16)
        if len(xs):
            img = img[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
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


_CARD_RATIO = CARD_H / CARD_W
# Margen de proporción lado largo / corto: la perspectiva de una cámara
# inclinada la deforma bastante.
_MIN_RATIO, _MAX_RATIO = 1.12, 1.68
_MAX_AREA_RATIO = 0.92
# Contorno / cuadrilátero: una carta lo rellena entero. Si queda mucho hueco,
# el cuadrilátero ha juntado la carta con otra cosa (soporte, borde de la mesa).
_MIN_FILL = 0.85
_BORDER_MARGIN = 0.01


def _side_ratio(quad: np.ndarray) -> float:
    a, b, c, d = quad
    s1 = (np.linalg.norm(b - a) + np.linalg.norm(c - d)) / 2
    s2 = (np.linalg.norm(d - a) + np.linalg.norm(c - b)) / 2
    lo, hi = sorted((s1, s2))
    return hi / lo if lo else float("inf")


def _contour_quad(contour) -> np.ndarray:
    approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
    if len(approx) == 4 and cv2.isContourConvex(approx):
        return approx.reshape(4, 2).astype(np.float32)
    # Esquinas redondeadas o bordes parcialmente ocultos: rectángulo mínimo.
    return cv2.boxPoints(cv2.minAreaRect(contour)).astype(np.float32)


def _edge_maps(gray: np.ndarray):
    yield cv2.dilate(cv2.Canny(gray, 40, 140), np.ones((3, 3), np.uint8), iterations=2)
    # La carta tiene mucho detalle dentro y el fondo poco: cerrando los bordes
    # queda una mancha sólida, y la apertura le quita las líneas finas que se le
    # pegan (el canto del soporte, el borde de la mesa).
    width = gray.shape[1]
    close_k = max(5, int(width * 0.025)) | 1
    blob = cv2.morphologyEx(
        cv2.Canny(gray, 30, 100), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_k, close_k))
    )
    contours, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(blob)
    cv2.drawContours(filled, contours, -1, 255, cv2.FILLED)
    open_k = max(5, int(width * 0.03)) | 1
    yield cv2.morphologyEx(filled, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (open_k, open_k)))


def _card_candidates(small: np.ndarray):
    """Cuadriláteros con forma de carta: (no toca el borde de la foto, área, cuadrilátero)."""
    sh, sw = small.shape[:2]
    total = sh * sw
    margin = _BORDER_MARGIN * max(sh, sw)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    for edges in _edge_maps(gray):
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            if not (_MIN_AREA_RATIO * total <= area <= _MAX_AREA_RATIO * total):
                continue
            quad = _contour_quad(contour)
            quad_area = cv2.contourArea(quad)
            if quad_area <= 0 or area / quad_area < _MIN_FILL:
                continue
            if not (_MIN_RATIO <= _side_ratio(quad) <= _MAX_RATIO):
                continue
            inside = not (
                (quad[:, 0] < margin).any()
                or (quad[:, 1] < margin).any()
                or (quad[:, 0] > sw - 1 - margin).any()
                or (quad[:, 1] > sh - 1 - margin).any()
            )
            yield inside, area, quad


def _legacy_quad(small: np.ndarray, min_area: float) -> np.ndarray | None:
    """Detector original: el contorno grande con 4 lados (o su rectángulo mínimo)."""
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 40, 140), np.ones((3, 3), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    for contour in contours:
        if cv2.contourArea(contour) < min_area:
            break
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return approx.reshape(4, 2).astype(np.float32)
    if contours and cv2.contourArea(contours[0]) >= min_area:
        return cv2.boxPoints(cv2.minAreaRect(contours[0])).astype(np.float32)
    return None


def find_card_quad(img: np.ndarray) -> np.ndarray | None:
    """Devuelve las 4 esquinas de la carta (coordenadas de `img`) o None.

    Prefiere el cuadrilátero más grande con proporción de carta, bien relleno y
    que no toque el borde de la foto (el fondo oscuro alrededor de la carta
    también forma un rectángulo, pero más grande y cortado por el encuadre).
    """
    h, w = img.shape[:2]
    scale = min(1.0, _DETECT_MAX_SIDE / max(h, w))
    small = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    best = max(_card_candidates(small), key=lambda c: c[:2], default=None)
    quad = best[2] if best else _legacy_quad(small, _MIN_AREA_RATIO * small.shape[0] * small.shape[1])
    return None if quad is None else quad / scale


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
