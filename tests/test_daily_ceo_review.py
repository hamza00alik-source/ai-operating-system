import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.db import connect
from scripts import create_daily_ceo_review as daily


def test_daily_ceo_review_is_idempotent_for_utc_date(monkeypatch, capsys):
    class FixedDateTime:
        @staticmethod
        def now(tz):
            return datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)

    calls = {"created": 0, "scheduled": 0}

    def create_plan(payload):
        calls["created"] += 1
        run_id = "daily-review-test-run"
        with connect() as db:
            db.execute(
                """INSERT INTO company_runs
                   (id,title,description,status,created_at,updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (run_id, "Daily review test", "", "queued", "2026-11-06T12:00:00Z", "2026-11-06T12:00:00Z"),
            )
            db.execute(
                """INSERT INTO ceo_plan_metadata
                   (run_id,objective,planning_mode,selected_workstreams_json,
                    decision_log_json,created_at)
                   VALUES (?,?,?,?,?,?)""",
                (run_id, payload.objective, "test", "[]", "[]", "2026-11-06T12:00:00Z"),
            )
        return {"run_id": run_id, "limitations": ["internal-only"]}

    def schedule():
        calls["scheduled"] += 1
        return {"scheduled": 0, "model_enabled": False}

    monkeypatch.setattr(daily, "datetime", FixedDateTime)
    monkeypatch.setattr(daily, "create_ceo_plan", create_plan)
    monkeypatch.setattr(daily, "schedule_ready_steps", schedule)

    with TestClient(app):
        daily.main()
        first = json.loads(capsys.readouterr().out)
        daily.main()
        second = json.loads(capsys.readouterr().out)

    assert first["status"] == "created"
    assert first["model_enabled"] is False
    assert second["status"] == "already_created"
    assert calls == {"created": 1, "scheduled": 1}
