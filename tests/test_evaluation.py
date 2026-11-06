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
