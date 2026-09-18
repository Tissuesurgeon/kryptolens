from django.db import migrations

from apps.users.rls import disable_public_rls, enable_public_rls


def forwards(apps, schema_editor):
    enable_public_rls(schema_editor)


def backwards(apps, schema_editor):
    disable_public_rls(schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("sessions", "0001_initial"),
        ("cmc", "0002_initial"),
        ("events", "0002_initial"),
        ("lenses", "0005_agent_os"),
        ("notifications", "0001_initial"),
        ("users", "0004_enable_userpreference_rls"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
