from django.contrib import admin

from .models import CollectionEntry, Location


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "is_default", "position"]
    list_filter = ["kind"]


@admin.register(CollectionEntry)
class CollectionEntryAdmin(admin.ModelAdmin):
    list_display = ["card", "location", "quantity", "fake", "updated_at"]
    list_filter = ["fake", "location", "card__set_code"]
    search_fields = ["card__name", "card__card_number", "notes"]
    raw_id_fields = ["card"]
