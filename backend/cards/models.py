from django.db import models


class Card(models.Model):
    """Una impresión concreta: las alt-art/promos comparten card_number pero
    tienen su propio id en Bandai y su propio arte (y por tanto fingerprint)."""

    bandai_id = models.PositiveIntegerField(unique=True, help_text="ID de Bandai TCG+")
    card_number = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    set_code = models.CharField(max_length=32, blank=True, db_index=True)
    set_name = models.CharField(max_length=255, blank=True)
    rarity = models.CharField(max_length=64, blank=True, db_index=True)
    card_type = models.CharField(max_length=32, blank=True, db_index=True)
    color = models.CharField(max_length=64, blank=True, db_index=True)
    cost = models.CharField(max_length=32, blank=True)
    power = models.CharField(max_length=32, blank=True)
    text = models.TextField(blank=True)
    image_url = models.URLField(max_length=500, blank=True)
    # Cara trasera (Leaders y cartas de dos caras).
    back_name = models.CharField(max_length=255, blank=True)
    back_text = models.TextField(blank=True)
    image_back_url = models.URLField(max_length=500, blank=True)
    # Resto de card_config (Character, Era, Special Trait…) y regulaciones.
    attributes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["card_number", "bandai_id"]

    def __str__(self):
        return f"{self.card_number} {self.name}"


class CardFingerprint(models.Model):
    class Face(models.TextChoices):
        FRONT = "front", "Anverso"
        BACK = "back", "Reverso"
        # Foto propia confirmada por el usuario: sirve para impresiones que no
        # están en Bandai TCG+ (promos, premios de torneo) y para afinar el
        # reconocimiento con la cámara e iluminación reales.
        SCAN = "scan", "Foto confirmada"

    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="fingerprints")
    face = models.CharField(max_length=8, choices=Face.choices, default=Face.FRONT)
    # URL de la imagen oficial a partir de la que se calculó: si cambia, se recalcula.
    source_url = models.URLField(max_length=500, blank=True)
    scan = models.OneToOneField(
        "scans.Scan", null=True, blank=True, on_delete=models.SET_NULL, related_name="fingerprint"
    )
    phash = models.BigIntegerField()
    dhash = models.BigIntegerField()
    orb = models.BinaryField()
    orb_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Una huella oficial por cara; fotos confirmadas, las que haga falta.
            models.UniqueConstraint(
                fields=["card", "face"],
                condition=~models.Q(face="scan"),
                name="unique_card_face",
            ),
        ]

    def __str__(self):
        return f"{self.card.card_number} ({self.face})"
