import sqlite3

import pytest

from ai_os.audit import append_event
from ai_os.db import initialize_database
from ai_os.db_backup import create_database_backup, verify_sqlite_backup


def test_backup_is_consistent_and_contains_application_data(tmp_path, monkeypatch):
    database = tmp_path / "live.sqlite3"
    backup = tmp_path / "backups" / "snapshot.sqlite3"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()
    append_event("test-owner", "backup_test", "test", "backup-1", {"safe": True})

    with sqlite3.connect(database) as db:
        db.execute(
            "INSERT INTO tasks (id,title,description,department,status,created_at) "
            "VALUES ('task-1','Backup test','','general','queued','2026-11-06T00:00:00Z')"
        )

    result = create_database_backup(backup)

    assert result["verification"]["valid"] is True
    assert result["verification"]["audit_chain_valid"] is True
    assert result["verification"]["audit_events_checked"] >= 1
    assert result["size_bytes"] > 0
    with sqlite3.connect(backup) as db:
        assert db.execute("SELECT title FROM tasks WHERE id='task-1'").fetchone() == (
            "Backup test",
        )
    assert verify_sqlite_backup(backup)["valid"] is True


def test_backup_rejects_live_database_as_destination(tmp_path, monkeypatch):
    database = tmp_path / "live.sqlite3"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()

    with pytest.raises(ValueError, match="must differ"):
        create_database_backup(database)


def test_backup_verification_rejects_non_database_file(tmp_path):
    invalid = tmp_path / "not-a-database.sqlite3"
    invalid.write_text("not sqlite data")

    with pytest.raises(sqlite3.DatabaseError):
        verify_sqlite_backup(invalid)


def test_backup_rejects_in_memory_database(monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///:memory:")

    with pytest.raises(ValueError, match="In-memory"):
        create_database_backup("backup.sqlite3")


def test_backup_verification_detects_audit_chain_tampering(tmp_path, monkeypatch):
    database = tmp_path / "live.sqlite3"
    backup = tmp_path / "tampered.sqlite3"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()
    append_event("test-owner", "created", "test", "item-1", {"value": "original"})
    create_database_backup(backup)

    with sqlite3.connect(backup) as db:
        db.execute(
            "UPDATE audit_events SET details_json=? WHERE resource_id=?",
            ('{"value":"tampered"}', "item-1"),
        )

    result = verify_sqlite_backup(backup)
    assert result["integrity"] == ["ok"]
    assert result["audit_chain_valid"] is False
    assert result["valid"] is False
