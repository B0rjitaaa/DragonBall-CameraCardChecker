"""Descarga de imágenes oficiales y cálculo de fingerprints del catálogo."""

import logging

from django.db.models import Q

from vision import fingerprint as fp
from vision.preprocess import decode_image, normalize_reference

from .images import get_image
from .models import Card, CardFingerprint

logger = logging.getLogger(__name__)


def _faces(card: Card):
    if card.image_url:
        yield CardFingerprint.Face.FRONT, card.image_url
    if card.image_back_url:
        yield CardFingerprint.Face.BACK, card.image_back_url


def pending_faces(force: bool = False):
    """(card, face, url) cuyo fingerprint falta o se calculó con otra URL."""
    cards = Card.objects.exclude(Q(image_url="") & Q(image_back_url=""))
    current = {
        (f.card_id, f.face): f.source_url
        for f in CardFingerprint.objects.exclude(face=CardFingerprint.Face.SCAN).only(
            "card_id", "face", "source_url"
        )
    }
    for card in cards.iterator():
        for face, url in _faces(card):
            if force or current.get((card.id, face)) != url:
                yield card, face, url


def build_one(card: Card, face: str, url: str) -> CardFingerprint:
    image = normalize_reference(decode_image(get_image(url)))
    result = fp.compute(image)
    obj, _ = CardFingerprint.objects.update_or_create(
        card=card,
        face=face,
        defaults={
            "source_url": url,
            "phash": result.phash,
            "dhash": result.dhash,
            "orb": result.orb,
            "orb_count": result.orb_count,
        },
    )
    return obj


def build_pending(force: bool = False, limit: int | None = None) -> tuple[int, int]:
    """Calcula los fingerprints pendientes. Devuelve (ok, errores)."""
    ok = errors = 0
    for i, (card, face, url) in enumerate(pending_faces(force)):
        if limit is not None and i >= limit:
            break
        try:
            build_one(card, face, url)
            ok += 1
        except Exception as exc:  # noqa: BLE001 - una imagen rota no para el lote
            errors += 1
            logger.warning("Fingerprint %s/%s falló: %s", card.card_number, face, exc)
        if (ok + errors) % 500 == 0:
            logger.info("Fingerprints: %s ok, %s errores", ok, errors)
    logger.info("Fingerprints terminados: %s ok, %s errores", ok, errors)
    return ok, errors
