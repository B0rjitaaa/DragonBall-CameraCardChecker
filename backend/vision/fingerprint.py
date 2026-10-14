"""Hashes perceptuales (pHash/dHash) y descriptores ORB.

pHash y dHash se implementan con OpenCV + numpy (mismo algoritmo que la
librería `imagehash`) para no instalar scipy/PyWavelets en la Raspberry Pi.
Los hashes de 64 bits se guardan como enteros con signo (BigIntegerField).
"""

from dataclasses import dataclass

import cv2
import numpy as np

# Se ignora un margen del borde: todas las cartas tienen marcos parecidos y es
# donde más falla el recorte.
_INNER_MARGIN = 0.04
_ORB_FEATURES = 500


@dataclass
class Fingerprint:
    phash: int
    dhash: int
    orb: bytes
    orb_count: int


def _prepare_gray(card: np.ndarray) -> np.ndarray:
    h, w = card.shape[:2]
    my, mx = int(h * _INNER_MARGIN), int(w * _INNER_MARGIN)
    inner = card[my : h - my, mx : w - mx]
    gray = cv2.cvtColor(inner, cv2.COLOR_BGR2GRAY) if inner.ndim == 3 else inner
    # Normalización de contraste para compensar la iluminación de la captura.
    return cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)


def _bits_to_signed(bits: np.ndarray) -> int:
    value = 0
    for bit in bits.ravel():
        value = (value << 1) | int(bit)
    return value - (1 << 64) if value >= (1 << 63) else value


def phash(gray: np.ndarray) -> int:
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    low = cv2.dct(small)[:8, :8]
    return _bits_to_signed(low > np.median(low))


def dhash(gray: np.ndarray) -> int:
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    return _bits_to_signed(small[:, 1:] > small[:, :-1])


def orb_descriptors(gray: np.ndarray) -> np.ndarray:
    orb = cv2.ORB_create(nfeatures=_ORB_FEATURES)
    _, descriptors = orb.detectAndCompute(gray, None)
    if descriptors is None:
        return np.empty((0, 32), dtype=np.uint8)
    return descriptors


def compute(card: np.ndarray) -> Fingerprint:
    """Fingerprint de una carta ya normalizada (CARD_W x CARD_H)."""
    gray = _prepare_gray(card)
    desc = orb_descriptors(gray)
    return Fingerprint(
        phash=phash(gray),
        dhash=dhash(gray),
        orb=desc.tobytes(),
        orb_count=len(desc),
    )


def descriptors_from_bytes(data: bytes) -> np.ndarray:
    return np.frombuffer(bytes(data), dtype=np.uint8).reshape(-1, 32)


def hamming(hashes: np.ndarray, query: int) -> np.ndarray:
    """Distancia de Hamming vectorizada entre un array int64 y un hash."""
    q = np.array([query], dtype=np.int64).view(np.uint64)
    return np.bitwise_count(hashes.view(np.uint64) ^ q).astype(np.int32)
