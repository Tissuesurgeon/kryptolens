from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lenses", "0006_enable_public_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="lensrun",
            name="as_of",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="routine",
            name="name",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="routine",
            name="paused",
            field=models.BooleanField(default=False),
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
                ],
                max_length=32,
            ),
        ),
    ]
