import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("collection", "0002_locations"),
        ("scans", "0005_scan_copies"),
    ]

    operations = [
        migrations.RemoveField(model_name="scansession", name="condition"),
        migrations.AddField(
            model_name="scansession",
            name="location",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sessions",
                to="collection.location",
            ),
        ),
    ]
