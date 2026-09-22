from django.db import migrations

from apps.users.rls import disable_table_rls, enable_table_rls

TABLE = "lenses_observation"


def enable_observation_rls(apps, schema_editor):
    enable_table_rls(schema_editor, TABLE)


def disable_observation_rls(apps, schema_editor):
    disable_table_rls(schema_editor, TABLE)


class Migration(migrations.Migration):

    dependencies = [
        ("lenses", "0010_alter_result_kind"),
    ]

    operations = [
        migrations.RunPython(enable_observation_rls, disable_observation_rls),
    ]
