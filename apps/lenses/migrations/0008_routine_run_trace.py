from django.db import migrations, models
import django.db.models.deletion


def backfill_routines(apps, schema_editor):
    Routine = apps.get_model("lenses", "Routine")
    for routine in Routine.objects.select_related("lens").all():
        lens = routine.lens
        version = lens.versions.order_by("-version").first()
        fields = ["enabled"]
        routine.enabled = True
        if not routine.name:
            routine.name = lens.name
            fields.append("name")
        if version and not routine.lens_version_id:
            routine.lens_version_id = version.id
            fields.append("lens_version")
        routine.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ("lenses", "0007_agent_workspace"),
    ]

    operations = [
        migrations.AddField(
            model_name="routine",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="routine",
            name="enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="routine",
            name="last_run_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="routine",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddField(
            model_name="routine",
            name="lens_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="routines",
                to="lenses.lensversion",
            ),
        ),
        migrations.AddField(
            model_name="lensrun",
            name="objective",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="lensrun",
            name="routine",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="runs",
                to="lenses.routine",
            ),
        ),
        migrations.AlterField(
            model_name="lensrun",
            name="stage",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("loading_policy", "Loading policy"),
                    ("planning", "Planning"),
                    ("trigger_check", "Trigger check"),
                    ("fetching_cmc", "Fetching CMC"),
                    ("evaluating", "Evaluating"),
                    ("analyzing", "Analyzing"),
                    ("scoring", "Scoring"),
                    ("investigating", "Investigating"),
                    ("generating_report", "Generating report"),
                    ("verifying", "Verifying"),
                    ("repairing", "Repairing"),
                    ("notifying", "Notifying"),
                    ("complete", "Complete"),
                    ("error", "Error"),
                ],
                default="queued",
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="conversationitem",
            name="item_type",
            field=models.CharField(
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
                    ("plan", "Plan"),
                    ("evidence", "Evidence"),
                    ("verification", "Verification"),
                    ("execution_receipt", "Execution receipt"),
                    ("cmc_activity", "CMC activity"),
                    ("routine_proposal", "Routine proposal"),
                    ("execution_trace", "Execution trace"),
                ],
                max_length=32,
            ),
        ),
        migrations.RunPython(backfill_routines, migrations.RunPython.noop),
    ]
