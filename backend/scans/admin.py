from django.contrib import admin

from .models import Scan


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ["id", "created_at", "source", "status", "matched_card", "confidence", "needs_review"]
    list_filter = ["status", "source", "needs_review", "method"]
    raw_id_fields = ["matched_card"]
    readonly_fields = ["candidates", "duration_ms", "created_at", "finished_at"]
