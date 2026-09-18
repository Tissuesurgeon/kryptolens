from django.db import migrations

from apps.users.rls import disable_table_rls, enable_table_rls

TABLE = "users_userpreference"


def enable_userpreference_rls(apps, schema_editor):
    enable_table_rls(schema_editor, TABLE)


def disable_userpreference_rls(apps, schema_editor):
    disable_table_rls(schema_editor, TABLE)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_enable_admin_log_rls"),
    ]

    operations = [
        migrations.RunPython(enable_userpreference_rls, disable_userpreference_rls),
    ]
