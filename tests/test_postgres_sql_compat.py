from ai_os.db import _postgres_sql


def test_postgres_translates_sqlite_placeholders():
    assert _postgres_sql("SELECT * FROM tasks WHERE id=? AND status=?") == (
        "SELECT * FROM tasks WHERE id=%s AND status=%s"
    )


def test_postgres_translates_autoincrement_primary_keys():
    assert _postgres_sql(
        "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)"
    ) == "CREATE TABLE events (id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL)"


def test_postgres_translates_pragma_table_info():
    statement, parameters = _postgres_sql("PRAGMA table_info(agent_runs)")
    assert "information_schema.columns" in statement
    assert "column_name AS name" in statement
    assert parameters == ("agent_runs",)
