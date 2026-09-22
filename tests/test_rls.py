from types import SimpleNamespace

from apps.users.rls import PUBLIC_TABLES, disable_table_rls, enable_public_rls, enable_table_rls


class _Editor:
    def __init__(self, vendor):
        self.connection = SimpleNamespace(vendor=vendor)
        self.statements = []

    def execute(self, sql):
        self.statements.append(sql)


def test_rls_is_noop_on_sqlite():
    editor = _Editor("sqlite")
    enable_table_rls(editor, "lenses_lens")
    disable_table_rls(editor, "lenses_lens")
    enable_public_rls(editor)
    assert editor.statements == []


def test_rls_enables_on_postgres():
    editor = _Editor("postgresql")
    enable_table_rls(editor, "lenses_lens")
    assert any("ENABLE ROW LEVEL SECURITY" in sql for sql in editor.statements)
    assert any("lenses_lens" in sql for sql in editor.statements)
    assert any("REVOKE ALL" in sql for sql in editor.statements)
    disable_table_rls(editor, "lenses_lens")
    assert any("DISABLE ROW LEVEL SECURITY" in sql for sql in editor.statements)


def test_public_rls_covers_lens_and_remaining_tables():
    assert "lenses_lens" in PUBLIC_TABLES
    assert "lenses_observation" in PUBLIC_TABLES
    editor = _Editor("postgresql")
    enable_public_rls(editor)
    joined = "\n".join(editor.statements)
    assert "lenses_lens" in joined
    assert joined.count("ENABLE ROW LEVEL SECURITY") == len(PUBLIC_TABLES)
