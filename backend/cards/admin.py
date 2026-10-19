from django.contrib import admin

from .models import Card, CardFingerprint, CatalogSync


class CardFingerprintInline(admin.TabularInline):
    model = CardFingerprint
    extra = 0
    fields = ["face", "source_url", "scan", "phash", "dhash", "orb_count", "updated_at"]
    readonly_fields = fields


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ["card_number", "name", "bandai_id", "set_code", "rarity", "card_type", "color"]
    list_filter = ["set_code", "rarity", "card_type", "color"]
    search_fields = ["card_number", "name", "=bandai_id"]
    inlines = [CardFingerprintInline]


@admin.register(CatalogSync)
class CatalogSyncAdmin(admin.ModelAdmin):
    list_display = ["started_at", "status", "full", "fetched", "created", "updated", "fingerprints", "fingerprint_errors"]
    list_filter = ["status", "full"]
    readonly_fields = [f.name for f in CatalogSync._meta.fields]
