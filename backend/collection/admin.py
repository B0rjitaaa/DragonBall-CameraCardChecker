from django.contrib import admin

from .models import CollectionEntry


@admin.register(CollectionEntry)
class CollectionEntryAdmin(admin.ModelAdmin):
    list_display = ["card", "quantity", "condition", "updated_at"]
    list_filter = ["condition", "card__set_code"]
    search_fields = ["card__name", "card__card_number"]
    raw_id_fields = ["card"]
