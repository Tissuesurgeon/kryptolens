from django.db import migrations

TABLE = "django_admin_log"


def enable_admin_log_rls(apps, schema_editor):
    """PostgREST exposes public tables. RLS with no policy denies anon/authenticated.

    Django's table owner still bypasses RLS. Do not FORCE ROW LEVEL SECURITY.
    SQLite (pytest) is a no-op.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY;")
    schema_editor.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON TABLE public.{TABLE} FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON TABLE public.{TABLE} FROM authenticated;
            END IF;
        END $$;
        """
    )


def disable_admin_log_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"ALTER TABLE public.{TABLE} DISABLE ROW LEVEL SECURITY;")


class Migration(migrations.Migration):

    dependencies = [
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("users", "0002_telegram_notify_results"),
    ]

    operations = [
        migrations.RunPython(enable_admin_log_rls, disable_admin_log_rls),
    ]
