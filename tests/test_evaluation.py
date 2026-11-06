import json
from pathlib import Path

from ai_os.evaluation import evaluate_specialist_report


def test_specialist_evaluation_regression_dataset():
    fixture_path = Path(__file__).parent / "fixtures" / "specialist_evaluations.json"
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))

    for case in cases:
        result = evaluate_specialist_report(case["report"])
        assert result["passed"] is case["expected_passed"], case["name"]
        assert 0 <= result["score"] <= 100
        assert result["checks"]
        assert result["limitations"]


def test_non_object_report_fails_closed():
    result = evaluate_specialist_report(["not", "an", "object"])

    assert result["passed"] is False
    assert result["critical_failures"] == ["object"]


def test_evaluation_does_not_mutate_report():
    report = {
        "status": "completed",
        "summary": "Reviewed supplied information.",
        "evidence": ["Source excerpt was supplied."],
        "blockers": [],
    }
    before = json.dumps(report, sort_keys=True)

    evaluate_specialist_report(report)

    assert json.dumps(report, sort_keys=True) == before



def test_evaluation_history_is_persisted_and_filterable(tmp_path, monkeypatch):
    from ai_os.db import connect, initialize_database
    from ai_os.evaluation import record_evaluation, list_evaluations, evaluation_summary

    database = tmp_path / "evaluation-history.sqlite3"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()
    with connect() as db:
        db.execute(
            "INSERT INTO company_runs (id,title,description,status,created_at,updated_at) "
            "VALUES ('run-1','Test run','','running','2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')"
        )
        db.execute(
            """INSERT INTO company_run_steps
            (run_id,step_key,agent_id,task,context,depends_on_json,status,position,created_at,updated_at)
            VALUES ('run-1','research','researcher','Research','','[]','assigned',1,
                    '2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')"""
        )

    result = evaluate_specialist_report({
        "status": "completed",
        "summary": "Reviewed supplied evidence.",
        "evidence": ["A supplied source excerpt."],
        "blockers": [],
    })
    saved = record_evaluation(
        run_id="run-1", step_key="research", agent_id="researcher", result=result
    )
    history = list_evaluations(agent_id="researcher")
    summary = evaluation_summary(agent_id="researcher")

    assert saved["evaluator_version"] == "1.0.0"
    assert saved["passed"] is True
    assert history[0]["id"] == saved["id"]
    assert history[0]["checks"]
    assert summary["total"] == 1
    assert summary["passed_count"] == 1
    assert summary["failed_count"] == 0


def test_evaluation_history_rejects_unknown_run_step(tmp_path, monkeypatch):
    import sqlite3
    from ai_os.db import initialize_database
    from ai_os.evaluation import record_evaluation

    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'empty.sqlite3'}")
    initialize_database()
    result = evaluate_specialist_report({
        "status": "blocked", "summary": "Blocked.", "evidence": [],
        "blockers": ["Missing input."],
    })

    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        record_evaluation(
            run_id="missing", step_key="missing", agent_id="researcher", result=result
        )



def test_evaluation_trends_compare_equal_windows_and_label_difficulty_caveat(tmp_path, monkeypatch):
    from ai_os.db import connect, initialize_database
    from ai_os.evaluation import record_evaluation, evaluation_trends

    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'trends.sqlite3'}")
    initialize_database()
    with connect() as db:
        db.execute(
            "INSERT INTO company_runs (id,title,description,status,created_at,updated_at) "
            "VALUES ('trend-run','Trend test','','running','2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')"
        )
        for index in range(10):
            db.execute(
                """INSERT INTO company_run_steps
                (run_id,step_key,agent_id,task,context,depends_on_json,status,position,created_at,updated_at)
                VALUES ('trend-run',?,'researcher','Task','','[]','completed',?,
                        '2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')""",
                (f"step-{index}", index),
            )
    for index in range(10):
        saved = record_evaluation(
            run_id="trend-run", step_key=f"step-{index}", agent_id="researcher",
            result={"score": 100 if index < 5 else 80, "passed": index < 5,
                    "critical_failures": [], "checks": [], "limitations": []},
        )
        with connect() as db:
            db.execute("UPDATE agent_evaluations SET created_at=? WHERE id=?",
                       (f"2026-11-06T00:00:{index:02d}Z", saved["id"]))
    trend = evaluation_trends(agent_id="researcher")["trends"][0]
    assert trend["sample_size"] == 10
    assert trend["previous_average"] == 100
    assert trend["recent_average"] == 80
    assert trend["delta"] == -20
    assert trend["signal"] == "provisional_regression"
    assert any("difficulty" in note for note in trend["limitations"])


def test_evaluation_trends_require_minimum_sample(tmp_path, monkeypatch):
    from ai_os.db import connect, initialize_database
    from ai_os.evaluation import record_evaluation, evaluation_trends

    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{tmp_path / 'small-trends.sqlite3'}")
    initialize_database()
    with connect() as db:
        db.execute(
            "INSERT INTO company_runs (id,title,description,status,created_at,updated_at) "
            "VALUES ('small-run','Small trend','','running','2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')"
        )
        db.execute(
            """INSERT INTO company_run_steps
            (run_id,step_key,agent_id,task,context,depends_on_json,status,position,created_at,updated_at)
            VALUES ('small-run','one','researcher','Task','','[]','completed',1,
                    '2026-11-06T00:00:00Z','2026-11-06T00:00:00Z')"""
        )
    record_evaluation(
        run_id="small-run", step_key="one", agent_id="researcher",
        result={"score": 100, "passed": True, "critical_failures": [], "checks": [], "limitations": []},
    )
    trend = evaluation_trends(agent_id="researcher")["trends"][0]
    assert trend["signal"] == "insufficient_data"
    assert trend["delta"] is None
