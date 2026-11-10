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
    assert parameters == ("agent_runs", "agent_runs")


def test_postgres_table_info_preserves_sqlite_column_metadata():
    statement, parameters = _postgres_sql("PRAGMA table_info(agent_runs)")
    assert "information_schema.columns" in statement
    assert 'AS "notnull"' in statement
    assert "AS dflt_value" in statement
    assert "AS pk" in statement
    assert "PRIMARY KEY" in statement
    assert parameters == ("agent_runs", "agent_runs")


def test_postgres_translates_insert_or_ignore():
    statement = _postgres_sql(
        "INSERT OR IGNORE INTO department_inbox_processing "
        "(message_id,status) VALUES(?,?)"
    )
    assert statement == (
        "INSERT INTO department_inbox_processing "
        "(message_id,status) VALUES(%s,%s) ON CONFLICT DO NOTHING"
    )


def test_postgres_placeholder_translation_preserves_quoted_question_marks():
    from ai_os.db import _replace_sqlite_placeholders

    sql = "SELECT '?' AS literal, \"?\" AS identifier, value FROM items WHERE id=? -- ?"
    assert _replace_sqlite_placeholders(sql) == (
        "SELECT '?' AS literal, \"?\" AS identifier, value FROM items WHERE id=%s -- ?"
    )


def test_postgres_placeholder_translation_preserves_block_comments():
    from ai_os.db import _replace_sqlite_placeholders

    assert _replace_sqlite_placeholders("SELECT ? /* ? */") == "SELECT %s /* ? */"


def test_live_postgres_adapter_when_test_database_is_configured(monkeypatch):
    import os
    import uuid
    import pytest
    from ai_os.db import connect

    database_url = os.getenv("AI_OS_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("Set AI_OS_TEST_POSTGRES_URL to run live PostgreSQL adapter checks.")
    monkeypatch.setenv("AI_OS_DATABASE_URL", database_url)
    table = "aios_adapter_test_" + uuid.uuid4().hex
    with connect() as db:
        db.execute(
            f"CREATE TEMP TABLE {table} "
            "(message_id TEXT PRIMARY KEY, status TEXT NOT NULL)"
        )
        first = db.execute(
            f"INSERT OR IGNORE INTO {table}(message_id,status) VALUES(?,?)",
            ("same-message", "processing"),
        )
        second = db.execute(
            f"INSERT OR IGNORE INTO {table}(message_id,status) VALUES(?,?)",
            ("same-message", "processing"),
        )
        assert first.rowcount == 1
        assert second.rowcount == 0
        metadata = list(db.execute(f"PRAGMA table_info({table})"))
        assert {column["name"] for column in metadata} == {"message_id", "status"}
        assert next(column for column in metadata if column["name"] == "message_id")["pk"] == 1
