"""Matching de una captura contra el índice de fingerprints del catálogo.

1. Hash perceptual: distancia pHash + dHash (0-128) contra todo el catálogo,
   vectorizado con numpy (milisegundos incluso con >10k cartas en la Pi).
2. Si la mejor distancia supera el umbral o el segundo candidato está muy
   cerca, se reordenan los N mejores con ORB (más lento, más robusto).
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import fingerprint as fp
from .preprocess import extract_card

_ORB_RATIO = 0.75
# Nº de coincidencias ORB "buenas" a partir del cual la confianza es 1.0.
_ORB_FULL_CONFIDENCE = 60
# Margen mínimo de distancia entre 1º y 2º para no considerarlo ambiguo.
_AMBIGUITY_MARGIN = 6


@dataclass
class FingerprintIndex:
    ids: np.ndarray  # pk de CardFingerprint
    card_ids: np.ndarray
    phashes: np.ndarray  # int64
    dhashes: np.ndarray  # int64

    @classmethod
    def from_rows(cls, rows):
        """rows: iterable de (fingerprint_id, card_id, phash, dhash)."""
        rows = list(rows)
        if not rows:
            empty = np.empty(0, dtype=np.int64)
            return cls(empty, empty, empty, empty)
        ids, card_ids, ph, dh = zip(*rows)
        return cls(
            np.array(ids, dtype=np.int64),
            np.array(card_ids, dtype=np.int64),
            np.array(ph, dtype=np.int64),
            np.array(dh, dtype=np.int64),
        )

    def __len__(self):
        return len(self.ids)


@dataclass
class Candidate:
    fingerprint_id: int
    card_id: int
    distance: int
    orb_matches: int | None = None

    @property
    def hash_confidence(self) -> float:
        return max(0.0, 1.0 - self.distance / 64)

    @property
    def orb_confidence(self) -> float:
        return min(1.0, (self.orb_matches or 0) / _ORB_FULL_CONFIDENCE)


@dataclass
class MatchResult:
    crop: np.ndarray
    card_detected: bool
    method: str  # "hash" | "orb" | "none"
    confidence: float = 0.0
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def best(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None


def _rank_by_hash(index: FingerprintIndex, card: np.ndarray, top: int) -> list[Candidate]:
    """Evalúa la carta y su rotación de 180º y se queda con la mejor distancia."""
    distances = None
    for variant in (card, cv2.rotate(card, cv2.ROTATE_180)):
        gray = fp._prepare_gray(variant)
        d = fp.hamming(index.phashes, fp.phash(gray)) + fp.hamming(index.dhashes, fp.dhash(gray))
        distances = d if distances is None else np.minimum(distances, d)

    order = np.argsort(distances, kind="stable")[:top]
    return [
        Candidate(int(index.ids[i]), int(index.card_ids[i]), int(distances[i])) for i in order
    ]


def _orb_good_matches(query: np.ndarray, reference: np.ndarray) -> int:
    if len(query) < 2 or len(reference) < 2:
        return 0
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    good = 0
    for pair in matcher.knnMatch(query, reference, k=2):
        if len(pair) == 2 and pair[0].distance < _ORB_RATIO * pair[1].distance:
            good += 1
    return good


def identify(
    img: np.ndarray,
    index: FingerprintIndex,
    load_orb: Callable[[list[int]], dict[int, bytes]],
    hash_threshold: int = 20,
    orb_candidates: int = 8,
) -> MatchResult:
    """Identifica la carta de `img` (BGR).

    `load_orb` recibe ids de CardFingerprint y devuelve {id: descriptores ORB};
    así solo se leen de la base de datos los descriptores de los candidatos.
    """
    crop, detected = extract_card(img)
    if len(index) == 0:
        return MatchResult(crop, detected, "none")

    candidates = _rank_by_hash(index, crop, max(orb_candidates, 5))
    best = candidates[0]
    ambiguous = (
        len(candidates) > 1 and candidates[1].distance - best.distance < _AMBIGUITY_MARGIN
    )
    if best.distance <= hash_threshold and not ambiguous:
        return MatchResult(crop, detected, "hash", best.hash_confidence, candidates)

    pool = candidates[:orb_candidates]
    orb_data = load_orb([c.fingerprint_id for c in pool])
    gray = fp._prepare_gray(crop)
    query_variants = [fp.orb_descriptors(gray), fp.orb_descriptors(cv2.rotate(gray, cv2.ROTATE_180))]
    for cand in pool:
        ref = fp.descriptors_from_bytes(orb_data.get(cand.fingerprint_id, b""))
        cand.orb_matches = max(_orb_good_matches(q, ref) for q in query_variants)

    pool.sort(key=lambda c: (-(c.orb_matches or 0), c.distance))
    top = pool[0]
    confidence = max(top.orb_confidence, top.hash_confidence)
    return MatchResult(crop, detected, "orb", confidence, pool + candidates[orb_candidates:])
