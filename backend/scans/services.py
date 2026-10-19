"""Integración del pipeline de visión con la base de datos."""

import logging
import threading
import time

import numpy as np
from django.conf import settings
from django.db import transaction
from django.db.models import Count, F, Max

from cards.models import Card, CardFingerprint
from collection.models import CollectionEntry
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


def warm_up(log: bool = True):
    """Identificación de prueba (forzando ORB).

    Al arrancar el worker: en la Raspberry Pi la primera identificación tardaba
    ~8 s más que las siguientes, porque OpenCV carga desde la SD el código de
    ORB/BFMatcher la primera vez que se usa.

    Periódicamente (tarea keep_warm): con la RAM justa, Linux manda al swap lo
    que lleva un rato sin usarse y el primer escaneo tras unos minutos parado
    tardaba 3-6 s en recuperarlo.
    """
    started = time.monotonic()
    noise = np.random.default_rng(0).integers(0, 256, (720, 1280, 3), dtype=np.uint8)
    identify(noise, get_index(), _load_orb, hash_threshold=-1, orb_candidates=2)
    if log:
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


def add_scan_to_collection(scan) -> None:
    """Suma 1 copia de la carta del escaneo a la colección (idempotente)."""
    if scan.added_to_collection or not scan.matched_card_id:
        return
    condition = scan.session.condition if scan.session_id else CollectionEntry.Condition.NEAR_MINT
    with transaction.atomic():
        entry, created = CollectionEntry.objects.select_for_update().get_or_create(
            card_id=scan.matched_card_id, condition=condition, defaults={"quantity": 1}
        )
        if not created:
            CollectionEntry.objects.filter(pk=entry.pk).update(quantity=F("quantity") + 1)
        scan.added_to_collection = True
        scan.collection_entry = entry
        scan.save(update_fields=["added_to_collection", "collection_entry"])


def remove_scan_from_collection(scan) -> None:
    """Deshace add_scan_to_collection: resta 1 copia (y borra la entrada si queda a 0)."""
    if not scan.added_to_collection:
        return
    with transaction.atomic():
        entry = (
            CollectionEntry.objects.select_for_update().filter(pk=scan.collection_entry_id).first()
        )
        if entry is not None:
            if entry.quantity <= 1:
                entry.delete()
            else:
                CollectionEntry.objects.filter(pk=entry.pk).update(quantity=F("quantity") - 1)
        scan.added_to_collection = False
        scan.collection_entry = None
        scan.save(update_fields=["added_to_collection", "collection_entry"])


def apply_burst_rules(scan) -> None:
    """Tras identificar un escaneo de una sesión de modo ráfaga."""
    if not scan.session_id or scan.status != scan.Status.DONE:
        return
    confidence = scan.confidence or 0.0
    if not scan.card_detected and confidence < settings.MATCH_MIN_CONFIDENCE:
        # Disparo sobre la zona vacía (se retiró la carta): no es una carta.
        scan.dismissed = True
        scan.save(update_fields=["dismissed"])
    elif _is_repeat(scan):
        # Misma carta que la anterior sin haber vaciado la zona: casi seguro
        # que se ha recolocado. Se pregunta en vez de sumar otra copia.
        scan.repeat_suspect = True
        scan.save(update_fields=["repeat_suspect"])
    elif confidence >= settings.AUTO_ADD_MIN_CONFIDENCE:
        add_scan_to_collection(scan)


def _is_repeat(scan) -> bool:
    if scan.after_empty or not scan.matched_card_id:
        return False
    previous = (
        scan.session.scans.filter(created_at__lt=scan.created_at, card_detected=True, dismissed=False)
        .exclude(pk=scan.pk)
        .order_by("-created_at")
        .first()
    )
    return previous is not None and previous.matched_card_id == scan.matched_card_id


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
