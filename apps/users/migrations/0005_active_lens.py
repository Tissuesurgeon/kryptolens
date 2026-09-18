import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("lenses", "0007_agent_workspace"),
        ("users", "0004_enable_userpreference_rls"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpreference",
            name="active_lens",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="active_for_preferences",
                to="lenses.lens",
            ),
        ),
    ]
