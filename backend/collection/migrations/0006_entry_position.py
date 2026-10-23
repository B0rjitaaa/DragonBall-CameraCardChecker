from django.db import migrations, models


def initial_order(apps, schema_editor):
    """Orden inicial dentro de cada ubicación: por número de carta (como se veía hasta ahora)."""
    Entry = apps.get_model("collection", "CollectionEntry")
    pos, last = {}, {}
    for entry in Entry.objects.select_related("card").order_by("location_id", "card__card_number", "card_id", "fake"):
        key = (entry.location_id, entry.card_id)
        if key not in pos:
            last[entry.location_id] = last.get(entry.location_id, 0) + 1
            pos[key] = last[entry.location_id]
        entry.position = pos[key]
        entry.save(update_fields=["position"])


class Migration(migrations.Migration):
    dependencies = [
        ("collection", "0005_fake"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectionentry",
            name="position",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(initial_order, migrations.RunPython.noop),
    ]
