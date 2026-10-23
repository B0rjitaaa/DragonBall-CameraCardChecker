from django.db import migrations, models


class Migration(migrations.Migration):
    """Copias falsas: todo lo existente queda como auténtico (fake=False)."""

    dependencies = [
        ("collection", "0004_drop_condition"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectionentry",
            name="fake",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.RemoveConstraint(model_name="collectionentry", name="unique_card_location"),
        migrations.AddConstraint(
            model_name="collectionentry",
            constraint=models.UniqueConstraint(fields=("card", "location", "fake"), name="unique_card_location_fake"),
        ),
        migrations.AlterModelOptions(
            name="collectionentry",
            options={"ordering": ["card__card_number", "location", "fake"], "verbose_name_plural": "collection entries"},
        ),
    ]
