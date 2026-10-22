"""Ubicaciones (2/3): todo lo existente pasa a "Sin ubicar".

Las filas de una misma carta que solo se distinguían por el estado se funden
en una (sumando cantidades) y los escaneos que apuntaban a las fundidas pasan
a apuntar a la que queda.
"""
from django.db import migrations


def to_default_location(apps, schema_editor):
    Location = apps.get_model("collection", "Location")
    Entry = apps.get_model("collection", "CollectionEntry")
    Scan = apps.get_model("scans", "Scan")
    default = Location.objects.create(name="Sin ubicar", is_default=True)

    kept = {}
    for entry in Entry.objects.order_by("card_id", "-quantity", "id"):
        keep = kept.get(entry.card_id)
        if keep is None:
            entry.location = default
            entry.save(update_fields=["location"])
            kept[entry.card_id] = entry
            continue
        keep.quantity += entry.quantity
        if entry.notes and entry.notes not in keep.notes:
            keep.notes = f"{keep.notes}\n{entry.notes}".strip()
        keep.save(update_fields=["quantity", "notes"])
        Scan.objects.filter(collection_entry=entry).update(collection_entry=keep)
        entry.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("collection", "0002_locations"),
        ("scans", "0005_scan_copies"),
    ]

    operations = [
        migrations.RunPython(to_default_location, migrations.RunPython.noop),
    ]
