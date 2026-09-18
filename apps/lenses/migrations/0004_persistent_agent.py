from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0002_initial"),
        ("lenses", "0003_spec_close_artifacts"),
    ]

    operations = [
        migrations.AddField(
            model_name="lens",
            name="purpose",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="lensversion",
            name="job_definition_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="lensversion",
            name="workflow_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="lensversion",
            name="tool_permissions_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="lensrun",
            name="results_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="lensrun",
            name="workflow_json",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="lensrun",
            name="tools_used_json",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="lensrun",
            name="stage",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("loading_policy", "Loading policy"),
                    ("fetching_cmc", "Fetching CMC"),
                    ("evaluating", "Evaluating"),
                    ("analyzing", "Analyzing"),
                    ("scoring", "Scoring"),
                    ("complete", "Complete"),
                    ("error", "Error"),
                ],
                default="queued",
                max_length=24,
            ),
        ),
        migrations.CreateModel(
            name="Routine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("manual", "Manual"),
                            ("interval", "Interval"),
                            ("scheduled", "Scheduled"),
                            ("event_triggered", "Event triggered"),
                        ],
                        default="event_triggered",
                        max_length=24,
                    ),
                ),
                ("interval_minutes", models.PositiveIntegerField(default=15)),
                ("schedule_time", models.TimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "lens",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="routines",
                        to="lenses.lens",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Result",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("ranked_table", "Ranked table"),
                            ("market_summary", "Market summary"),
                            ("comparison", "Comparison"),
                            ("event", "Event"),
                            ("no_result", "No result"),
                            ("error", "Error"),
                        ],
                        max_length=24,
                    ),
                ),
                ("title", models.CharField(blank=True, max_length=200)),
                ("payload_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "lens",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="results",
                        to="lenses.lens",
                    ),
                ),
                (
                    "lens_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="results",
                        to="lenses.lensrun",
                    ),
                ),
                (
                    "lens_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="results",
                        to="lenses.lensversion",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ConversationItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "item_type",
                    models.CharField(
                        choices=[
                            ("user_message", "User"),
                            ("assistant_message", "Assistant"),
                            ("lens_created", "Lens created"),
                            ("job_created", "Job"),
                            ("workflow_created", "Workflow"),
                            ("routine_created", "Routine"),
                            ("status_update", "Status"),
                            ("scan_result", "Scan result"),
                            ("event_result", "Event"),
                            ("policy_diff", "Policy diff"),
                            ("execution_error", "Error"),
                        ],
                        max_length=32,
                    ),
                ),
                ("payload_json", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "event",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="events.event",
                    ),
                ),
                (
                    "lens",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conversation_items",
                        to="lenses.lens",
                    ),
                ),
                (
                    "lens_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="lenses.lensrun",
                    ),
                ),
                (
                    "lens_version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="lenses.lensversion",
                    ),
                ),
                (
                    "result",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="lenses.result",
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
    ]
