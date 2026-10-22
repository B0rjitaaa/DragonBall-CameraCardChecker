from django.contrib import admin

from .models import Scan, ScanSession


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ["id", "created_at", "source", "status", "matched_card", "confidence", "needs_review", "session", "added_to_collection", "dismissed"]
    list_filter = ["status", "source", "needs_review", "method", "added_to_collection", "dismissed"]
    raw_id_fields = ["matched_card", "session", "collection_entry"]
    readonly_fields = ["candidates", "duration_ms", "created_at", "finished_at"]


@admin.register(ScanSession)
class ScanSessionAdmin(admin.ModelAdmin):
    list_display = ["id", "started_at", "ended_at", "location"]
