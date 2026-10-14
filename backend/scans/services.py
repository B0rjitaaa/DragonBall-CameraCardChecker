"""Integración del pipeline de visión con la base de datos."""

import logging
import threading
import time

import numpy as np
from django.conf import settings
from django.db.models import Count, Max

from cards.models import Card, CardFingerprint
from vision import fingerprint as fp
from vision.matcher import FingerprintIndex, MatchResult, identify
from vision.preprocess import decode_image

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: dict = {"key": None, "index": None}


def _index_key():
    agg = CardFingerprint.objects.aggregate(n=Count("id"), last=Max("updated_at"))
    return agg["n"], agg["last"]


def get_index() -> FingerprintIndex:
    """Índice de hashes en memoria del worker; se recarga si cambia el catálogo."""
    key = _index_key()
    with _lock:
        if _cache["key"] != key:
            rows = CardFingerprint.objects.values_list("id", "card_id", "phash", "dhash")
            _cache["index"] = FingerprintIndex.from_rows(rows.iterator())
            _cache["key"] = key
        return _cache["index"]


def _load_orb(fingerprint_ids: list[int]) -> dict[int, bytes]:
    return dict(
        CardFingerprint.objects.filter(id__in=fingerprint_ids).values_list("id", "orb")
    )


def run_identification(img) -> MatchResult:
    return identify(
        img,
        get_index(),
        _load_orb,
        hash_threshold=settings.MATCH_HASH_THRESHOLD,
        orb_candidates=settings.MATCH_ORB_CANDIDATES,
    )


def warm_up():
    """Identificación de prueba (forzando ORB) al arrancar el worker.

    En la Raspberry Pi la primera identificación tardaba ~8 s más que las
    siguientes: OpenCV carga desde la SD el código de ORB/BFMatcher la primera
    vez que se usa. Así lo paga el arranque y no el primer escaneo.
    """
    started = time.monotonic()
    noise = np.random.default_rng(0).integers(0, 256, (720, 1280, 3), dtype=np.uint8)
    identify(noise, get_index(), _load_orb, hash_threshold=-1, orb_candidates=2)
    logger.info("Worker precalentado en %.1f s", time.monotonic() - started)


def learn_from_scan(scan, card) -> CardFingerprint:
    """Guarda el recorte del escaneo como fingerprint de `card` (una por escaneo)."""
    with scan.cropped_image.open("rb") as fh:
        crop = decode_image(fh.read())
    result = fp.compute(crop)
    fingerprint, _ = CardFingerprint.objects.update_or_create(
        scan=scan,
        defaults={
            "card": card,
            "face": CardFingerprint.Face.SCAN,
            "phash": result.phash,
            "dhash": result.dhash,
            "orb": result.orb,
            "orb_count": result.orb_count,
        },
    )
    return fingerprint


def serialize_candidates(result: MatchResult, limit: int = 5) -> list[dict]:
    """Candidatos únicos por carta, con los datos necesarios para la UI."""
    seen, unique = set(), []
    for cand in result.candidates:
        if cand.card_id not in seen:
            seen.add(cand.card_id)
            unique.append(cand)
        if len(unique) == limit:
            break

    cards = Card.objects.in_bulk([c.card_id for c in unique])
    output = []
    for cand in unique:
        card = cards.get(cand.card_id)
        if card is None:
            continue
        output.append(
            {
                "card_id": card.id,
                "card_number": card.card_number,
                "name": card.name,
                "image_url": card.image_url,
                "distance": cand.distance,
                "orb_matches": cand.orb_matches,
                "score": round(
                    max(cand.hash_confidence, cand.orb_confidence)
                    if cand.orb_matches is not None
                    else cand.hash_confidence,
                    3,
                ),
            }
        )
    return output
