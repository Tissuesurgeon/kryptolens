from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("lenses", "0008_routine_run_trace"),
    ]

    operations = [
        migrations.CreateModel(
            name="Observation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("asset_id", models.IntegerField(default=0)),
                ("symbol", models.CharField(blank=True, max_length=24)),
                ("observed_at", models.DateTimeField()),
                ("fields_json", models.JSONField(blank=True, default=dict)),
                ("source_endpoint", models.CharField(blank=True, max_length=160)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "lens_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="observations",
                        to="lenses.lensrun",
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
    ]
