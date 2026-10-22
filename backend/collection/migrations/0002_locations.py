"""Ubicaciones (1/3): tabla nueva y campo `location` aún opcional.

Va en tres migraciones porque Postgres no deja alterar la tabla en la misma
transacción en la que se han borrado filas (las fusionadas en 0003).
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("collection", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Location",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[("deck", "Mazo"), ("binder", "Archivador"), ("storage", "Almacén"), ("other", "Otro")],
                        default="other",
                        max_length=8,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("is_default", models.BooleanField(default=False)),
                ("position", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-is_default", "position", "name"]},
        ),
        migrations.AddConstraint(
            model_name="location",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True)), fields=("is_default",), name="single_default_location"
            ),
        ),
        migrations.AddField(
            model_name="collectionentry",
            name="location",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT, related_name="entries", to="collection.location"
            ),
        ),
    ]
