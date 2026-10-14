"""Cartas y fotos sintéticas para tests (sin red ni imágenes reales)."""

import cv2
import numpy as np

from vision.preprocess import CARD_H, CARD_W


def make_card(seed: int) -> np.ndarray:
    """Carta con borde y un "arte" aleatorio suave, distinto por semilla."""
    rng = np.random.default_rng(seed)
    art = rng.integers(0, 256, size=(11, 8, 3), dtype=np.uint8)
    art = cv2.resize(art, (CARD_W, CARD_H), interpolation=cv2.INTER_CUBIC)
    for _ in range(6):
        center = (int(rng.integers(30, CARD_W - 30)), int(rng.integers(30, CARD_H - 30)))
        color = tuple(int(c) for c in rng.integers(0, 256, 3))
        cv2.circle(art, center, int(rng.integers(10, 50)), color, -1)
    cv2.rectangle(art, (0, 0), (CARD_W - 1, CARD_H - 1), (20, 20, 20), 12)
    return art


def make_photo(card: np.ndarray, rotate_180: bool = False) -> np.ndarray:
    """Coloca la carta en perspectiva sobre un fondo claro, como bajo la cámara."""
    if rotate_180:
        card = cv2.rotate(card, cv2.ROTATE_180)
    photo_w, photo_h = 1280, 720
    src = np.float32([[0, 0], [CARD_W, 0], [CARD_W, CARD_H], [0, CARD_H]])
    dst = np.float32([[520, 110], [800, 130], [790, 620], [500, 600]])
    matrix = cv2.getPerspectiveTransform(src, dst)
    background = np.full((photo_h, photo_w, 3), 225, dtype=np.uint8)
    warped = cv2.warpPerspective(card, matrix, (photo_w, photo_h))
    mask = cv2.warpPerspective(
        np.full((CARD_H, CARD_W), 255, np.uint8), matrix, (photo_w, photo_h)
    )
    photo = np.where(mask[..., None] > 0, warped, background)
    # Algo de brillo y ruido de sensor.
    photo = cv2.convertScaleAbs(photo, alpha=0.9, beta=15)
    noise = np.random.default_rng(0).normal(0, 4, photo.shape)
    return np.clip(photo.astype(np.float32) + noise, 0, 255).astype(np.uint8)
