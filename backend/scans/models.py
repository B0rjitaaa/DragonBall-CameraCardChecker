from django.db import models
from django.utils import timezone

from cards.models import Card
from collection.models import CollectionEntry, Location


def scan_upload_to(instance, filename):
    # created_at aún no existe cuando se guarda la imagen al crear el Scan.
    return f"scans/{timezone.now():%Y/%m}/{filename}"


class ScanSession(models.Model):
    """Sesión de modo ráfaga: el usuario va cambiando cartas bajo la cámara y
    las identificadas con confianza suficiente se añaden solas a la colección."""

    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    # Dónde entran las cartas que se añaden (vacío = "Sin ubicar").
    location = models.ForeignKey(
        Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="sessions"
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Sesión #{self.pk} ({self.started_at:%Y-%m-%d %H:%M})"


class Scan(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PROCESSING = "processing", "Procesando"
        DONE = "done", "Completado"
        FAILED = "failed", "Error"

    class Source(models.TextChoices):
        UPLOAD = "upload", "Imagen subida"
        CAMERA = "camera", "Cámara"

    source = models.CharField(max_length=8, choices=Source.choices, default=Source.UPLOAD)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    image = models.ImageField(upload_to=scan_upload_to, blank=True)
    cropped_image = models.ImageField(upload_to=scan_upload_to, blank=True)
    card_detected = models.BooleanField(default=False)
    matched_card = models.ForeignKey(
        Card, null=True, blank=True, on_delete=models.SET_NULL, related_name="scans"
    )
    confidence = models.FloatField(null=True, blank=True)
    # Confianza por debajo de MATCH_MIN_CONFIDENCE: requiere revisión manual.
    needs_review = models.BooleanField(default=False)
    # El usuario ha confirmado (o corregido) la carta: su recorte se guarda
    # como fingerprint de esa carta.
    confirmed = models.BooleanField(default=False)
    session = models.ForeignKey(
        ScanSession, null=True, blank=True, on_delete=models.SET_NULL, related_name="scans"
    )
    # Modo ráfaga: si se añadió a la colección (y a qué entrada, para deshacer).
    added_to_collection = models.BooleanField(default=False)
    collection_entry = models.ForeignKey(
        CollectionEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="scans"
    )
    # Copias que suma este escaneo (o sumará al confirmarlo).
    copies = models.PositiveSmallIntegerField(default=1)
    # Descartado: deshecho por el usuario o disparo sin carta (zona vacía).
    dismissed = models.BooleanField(default=False)
    # Lo envía el navegador: ¿quedó vacía la zona desde la captura anterior?
    # Si no, y sale la misma carta que la anterior, lo más probable es que se
    # haya recolocado la misma carta: no se añade sola ("¿Otra copia?").
    after_empty = models.BooleanField(default=True)
    repeat_suspect = models.BooleanField(default=False)
    method = models.CharField(max_length=8, blank=True)
    candidates = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Scan #{self.pk} ({self.status})"
