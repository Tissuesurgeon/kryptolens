from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lenses", "0002_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="lens",
            name="is_demo_scenario",
        ),
        migrations.RemoveField(
            model_name="lens",
            name="is_example",
        ),
        migrations.AddField(
            model_name="lensversion",
            name="compile_report_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="lensrun",
            name="stage",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("loading_policy", "Loading policy"),
                    ("fetching_cmc", "Fetching CMC"),
                    ("evaluating", "Evaluating"),
                    ("scoring", "Scoring"),
                    ("complete", "Complete"),
                    ("error", "Error"),
                ],
                default="queued",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="lensrun",
            name="summary_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="lensrun",
            name="near_matches_json",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
