"""Postgres RLS helpers for tables exposed in the public schema.

PostgREST can read public tables that lack RLS. Enable RLS with no policy so
anon/authenticated are denied. Django's table owner still bypasses RLS.
Do not FORCE ROW LEVEL SECURITY. SQLite is a no-op.
"""

PUBLIC_TABLES = (
    "lenses_lens",
    "lenses_lensversion",
    "lenses_lensrun",
    "lenses_routine",
    "lenses_result",
    "lenses_conversationitem",
    "lenses_job",
    "lenses_artifact",
    "lenses_agenttask",
    "lenses_observation",
    "lenses_evidence",
    "lenses_verificationrecord",
    "lenses_approvalrequest",
    "events_event",
    "cmc_cmccalllog",
    "notifications_notification",
    "users_user",
    "users_userpreference",
    "users_user_groups",
    "users_user_user_permissions",
    "django_admin_log",
    "django_session",
    "django_content_type",
    "django_migrations",
    "auth_permission",
    "auth_group",
    "auth_group_permissions",
)


def enable_table_rls(schema_editor, table: str) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"ALTER TABLE IF EXISTS public.{table} ENABLE ROW LEVEL SECURITY;")
    schema_editor.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('public.{table}') IS NULL THEN
                RETURN;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON TABLE public.{table} FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON TABLE public.{table} FROM authenticated;
            END IF;
        END $$;
        """
    )


def disable_table_rls(schema_editor, table: str) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"ALTER TABLE IF EXISTS public.{table} DISABLE ROW LEVEL SECURITY;")


def enable_public_rls(schema_editor) -> None:
    for table in PUBLIC_TABLES:
        enable_table_rls(schema_editor, table)


def disable_public_rls(schema_editor) -> None:
    for table in reversed(PUBLIC_TABLES):
        disable_table_rls(schema_editor, table)
