from __future__ import annotations

import os

import pytest


def test_named_sqlite_parameters_translate_for_psycopg():
    from ai_os.db import _replace_sqlite_placeholders

    statement = (
        "SELECT :task_id, ?, ':literal?', \"quoted:name\", value::text "
        "-- :comment\n/* :block */ WHERE owner=:owner_id"
    )
    assert _replace_sqlite_placeholders(statement) == (
        "SELECT %(task_id)s, %s, ':literal?', \"quoted:name\", value::text "
        "-- :comment\n/* :block */ WHERE owner=%(owner_id)s"
    )


def test_postgres_schema_initialization_and_runtime_queries(monkeypatch):
    database_url = os.getenv("AI_OS_TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("AI_OS_TEST_POSTGRES_URL is only configured in the PostgreSQL CI job.")

    from ai_os import db
    from ai_os.config import Settings

    monkeypatch.setattr(db, "get_settings", lambda: Settings(database_url=database_url))

    # Apply the standalone baseline to a disposable PostgreSQL database first.
    from pathlib import Path
    migration = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "migrations"
        / "20261110160000_aios_initial_schema.sql"
    )
    assert migration.is_file()
    with db.connect() as connection:
        connection.executescript(migration.read_text(encoding="utf-8"))
        table_count = connection.execute(
            """SELECT COUNT(*) AS n FROM information_schema.tables
               WHERE table_schema='public' AND table_type='BASE TABLE'"""
        ).fetchone()["n"]
        index_count = connection.execute(
            """SELECT COUNT(*) AS n FROM pg_indexes
               WHERE schemaname='public' AND indexname LIKE 'idx_%'"""
        ).fetchone()["n"]
        rls_count = connection.execute(
            """SELECT COUNT(*) AS n FROM pg_class c
               JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity"""
        ).fetchone()["n"]
        assert table_count == 22
        assert index_count == 23
        assert rls_count == 22

    # The runtime initializer must safely coexist with the migrated final schema.
    db.initialize_database()

    from ai_os.workflows import initialize_workflows
    initialize_workflows()

    # Exercise the PRAGMA compatibility path used by agent_runtime and workflows.
    with db.connect() as connection:
        columns = list(connection.execute("PRAGMA table_info(agent_runs)"))
        assert "task_id" in {column["name"] for column in columns}
        assert all("notnull" in column.keys() for column in columns)

        # Exercise named parameters against psycopg, as used by service.py and discovery.py.
        from uuid import uuid4
        task_id = str(uuid4())
        connection.execute(
            """INSERT INTO tasks
               (id,title,description,department,business_id,status,created_at)
               VALUES (:id,:title,:description,:department,:business_id,:status,:created_at)""",
            {
                "id": task_id,
                "title": "PostgreSQL adapter regression",
                "description": "synthetic CI fixture",
                "department": "testing",
                "business_id": "core",
                "status": "queued",
                "created_at": "2026-01-01T00:00:00+00:00",
            },
        )
        found = connection.execute(
            "SELECT id FROM tasks WHERE id=:task_id", {"task_id": task_id}
        ).fetchone()
        assert found["id"] == task_id

    # This production code path uses SQLite named placeholders and a dict.
    from ai_os.discovery import create_scan
    scan = create_scan(["agent-frameworks"])
    assert scan["status"] == "queued"

    with db.connect() as connection:
        row = connection.execute(
            "SELECT categories FROM discovery_scans WHERE id=:scan_id",
            {"scan_id": scan["id"]},
        ).fetchone()
        assert row["categories"] == '["agent-frameworks"]'
