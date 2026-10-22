"""Ubicaciones (3/3): fuera el estado; la ubicación pasa a ser obligatoria."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("collection", "0003_locations_data"),
    ]

    operations = [
        migrations.RemoveConstraint(model_name="collectionentry", name="unique_card_condition"),
        migrations.RemoveField(model_name="collectionentry", name="condition"),
        migrations.AlterField(
            model_name="collectionentry",
            name="location",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="entries", to="collection.location"
            ),
        ),
        migrations.AddConstraint(
            model_name="collectionentry",
            constraint=models.UniqueConstraint(fields=("card", "location"), name="unique_card_location"),
        ),
        migrations.AlterModelOptions(
            name="collectionentry",
            options={"ordering": ["card__card_number", "location"], "verbose_name_plural": "collection entries"},
        ),
    ]
