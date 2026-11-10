from fastapi.testclient import TestClient

from ai_os.api import app


def test_supabase_status_never_exposes_database_url(monkeypatch):
    from ai_os import supabase_integration

    monkeypatch.setenv(
        "AI_OS_DATABASE_URL",
        "postgresql://owner:very-secret-password@aws-0-test.pooler.supabase.com:5432/postgres?sslmode=require",
    )
    monkeypatch.setenv("SUPABASE_URL", "https://example-project.supabase.co")
    payload = supabase_integration.status()

    assert payload["database_configured"] is True
    assert payload["database_provider"] == "supabase"
    assert payload["project_url_configured"] is True
    assert payload["credentials_exposed"] is False
    assert "very-secret-password" not in str(payload)
    assert "example-project" not in str(payload)


def test_supabase_status_reports_non_postgres_as_unconfigured(monkeypatch):
    from ai_os import supabase_integration

    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///./ai_os.db")
    payload = supabase_integration.status()
    assert payload["database_configured"] is False
    assert payload["database_provider"] is None


def test_supabase_connection_probe_is_read_only_and_owner_route(monkeypatch):
    from ai_os import supabase_integration

    captured = {}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement):
            captured["statement"] = statement

        def fetchone(self):
            return (1,)

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return Cursor()

    def fake_connect(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return Connection()

    monkeypatch.setenv(
        "AI_OS_DATABASE_URL",
        "postgresql://owner:secret@db.example.supabase.co:5432/postgres",
    )
    monkeypatch.setattr(supabase_integration.psycopg, "connect", fake_connect)
    payload = supabase_integration.test_connection()

    assert payload["connected"] is True
    assert payload["schema_changed"] is False
    assert captured["statement"] == "SELECT 1"
    assert captured["kwargs"] == {"connect_timeout": 5, "sslmode": "require"}


def test_supabase_connection_probe_fails_closed_without_database_url(monkeypatch):
    from ai_os import supabase_integration
    from fastapi import HTTPException

    monkeypatch.setenv("AI_OS_DATABASE_URL", "sqlite:///./ai_os.db")
    try:
        supabase_integration.test_connection()
        raise AssertionError("A SQLite URL must not be treated as a Supabase connection.")
    except HTTPException as exc:
        assert exc.status_code == 409


def test_supabase_connection_probe_sanitizes_driver_error(monkeypatch):
    from ai_os import supabase_integration

    def fail_connect(*args, **kwargs):
        raise RuntimeError("postgresql://owner:password@private-host")

    monkeypatch.setenv(
        "AI_OS_DATABASE_URL",
        "postgresql://owner:secret@db.example.supabase.co:5432/postgres",
    )
    monkeypatch.setattr(supabase_integration.psycopg, "connect", fail_connect)
    payload = supabase_integration.test_connection()

    assert payload["connected"] is False
    assert payload["error_type"] == "RuntimeError"
    assert "password" not in str(payload)
    assert "private-host" not in str(payload)


def test_supabase_routes_require_owner_auth(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "test-owner-key")
    with TestClient(app) as client:
        denied = client.get("/integrations/supabase/status")
        allowed = client.get(
            "/integrations/supabase/status",
            headers={"X-API-Key": "test-owner-key"},
        )
    assert denied.status_code == 401
    assert allowed.status_code == 200
