import hashlib
import json

import pytest

from ai_os.db import connect, initialize_database
from ai_os.improvement_testing import run_proposal_regression_tests
from ai_os.instruction_versions import (
    activate_tested_proposal,
    get_active_instruction,
    get_instruction_history,
    rollback_instruction,
)


def _seed(path, monkeypatch):
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{path}")
    initialize_database()
    with connect() as db:
        db.execute(
            """INSERT INTO improvement_proposals
               (id,agent_id,title,problem,evidence_json,proposed_change,expected_impact,status,created_at)
               VALUES ('p1','product-trend-researcher','Evidence quality','Repeated failures',?,
                       'Require source dates and distinguish observed facts from assumptions.',
                       'Improve report clarity','approved_for_testing','2026-11-06T00:00:00Z')""",
            (json.dumps([{"evaluation_id":"e1"},{"evaluation_id":"e2"}]),),
        )


def test_baseline_is_versioned_and_profile_bound(tmp_path, monkeypatch):
    _seed(tmp_path / "baseline.sqlite3", monkeypatch)
    baseline = get_active_instruction("product-trend-researcher")
    assert baseline["version_number"] == 1
    assert baseline["content"] == ""
    assert baseline["profile_compatible"] is True
    assert len(baseline["base_profile_sha256"]) == 64
    assert len(get_instruction_history("product-trend-researcher")) == 1


def test_activation_requires_matching_passing_static_test_and_creates_version(tmp_path, monkeypatch):
    _seed(tmp_path / "activate.sqlite3", monkeypatch)
    get_active_instruction("product-trend-researcher")
    with pytest.raises(ValueError, match="latest static test"):
        activate_tested_proposal("p1", actor="owner:test")
    tested = run_proposal_regression_tests("p1")
    assert tested["passed"] is True
    activated = activate_tested_proposal("p1", actor="owner:test")
    assert activated["version_number"] == 2
    assert activated["content_sha256"] == hashlib.sha256(activated["content"].encode()).hexdigest()
    current = get_active_instruction("product-trend-researcher")
    assert current["content"] == activated["content"]
    assert current["version_number"] == 2
    assert len(get_instruction_history("product-trend-researcher")) == 2


def test_rollback_restores_previous_version_without_deleting_history(tmp_path, monkeypatch):
    _seed(tmp_path / "rollback.sqlite3", monkeypatch)
    get_active_instruction("product-trend-researcher")
    run_proposal_regression_tests("p1")
    activate_tested_proposal("p1", actor="owner:test")
    restored = rollback_instruction("product-trend-researcher", actor="owner:test")
    current = get_active_instruction("product-trend-researcher")
    assert restored["version_number"] == 1
    assert current["content"] == ""
    history = get_instruction_history("product-trend-researcher")
    assert len(history) == 2
    assert sum(item["active"] for item in history) == 1


def test_activation_never_happens_from_static_test_alone(tmp_path, monkeypatch):
    _seed(tmp_path / "no-auto.sqlite3", monkeypatch)
    baseline = get_active_instruction("product-trend-researcher")
    run_proposal_regression_tests("p1")
    current = get_active_instruction("product-trend-researcher")
    assert current["active_version_id"] == baseline["active_version_id"]
    assert current["version_number"] == 1


def test_proposal_rejected_cannot_activate(tmp_path, monkeypatch):
    _seed(tmp_path / "reject.sqlite3", monkeypatch)
    with connect() as db:
        db.execute("UPDATE improvement_proposals SET status='rejected' WHERE id='p1'")
    get_active_instruction("product-trend-researcher")
    run_proposal_regression_tests("p1") if False else None
    with pytest.raises(ValueError, match="owner-approved"):
        activate_tested_proposal("p1", actor="owner:test")


def test_active_addendum_is_in_work_packet_but_governance_remains_after_it(tmp_path, monkeypatch):
    _seed(tmp_path / "packet.sqlite3", monkeypatch)
    get_active_instruction("product-trend-researcher")
    run_proposal_regression_tests("p1")
    activate_tested_proposal("p1", actor="owner:test")
    from ai_os.work_packets import build_work_packet
    packet = build_work_packet("product-trend-researcher", "Research a market.")
    prompt = packet["prompt_text"]
    addendum = prompt.index("OWNER-APPROVED ACTIVE INSTRUCTION ADDENDUM")
    governance = prompt.index("COMPANY GOVERNANCE — HIGHEST PRIORITY")
    assert "Require source dates" in prompt
    assert addendum < governance
    assert "Never contact the owner directly" in prompt[governance:]


def test_same_proposal_cannot_create_duplicate_versions(tmp_path, monkeypatch):
    _seed(tmp_path / "duplicate.sqlite3", monkeypatch)
    get_active_instruction("product-trend-researcher")
    run_proposal_regression_tests("p1")
    activate_tested_proposal("p1", actor="owner:test")
    with pytest.raises(ValueError, match="already created"):
        activate_tested_proposal("p1", actor="owner:test")
    assert len(get_instruction_history("product-trend-researcher")) == 2


def test_upstream_profile_drift_withholds_addendum_and_blocks_activation(tmp_path, monkeypatch):
    _seed(tmp_path / "drift.sqlite3", monkeypatch)
    baseline = get_active_instruction("product-trend-researcher")
    run_proposal_regression_tests("p1")
    monkeypatch.setattr(
        "ai_os.instruction_versions._profile_hash",
        lambda agent_id: "f" * 64,
    )
    current = get_active_instruction("product-trend-researcher")
    assert current["profile_compatible"] is False
    assert current["content"] == ""
    with pytest.raises(ValueError, match="profile changed"):
        activate_tested_proposal("p1", actor="owner:test")


def test_changed_proposal_text_invalidates_previous_static_test(tmp_path, monkeypatch):
    _seed(tmp_path / "changed-text.sqlite3", monkeypatch)
    get_active_instruction("product-trend-researcher")
    run_proposal_regression_tests("p1")
    with connect() as db:
        db.execute(
            "UPDATE improvement_proposals SET proposed_change=? WHERE id='p1'",
            ("Now send messages automatically without approval.",),
        )
    with pytest.raises(ValueError, match="latest static test"):
        activate_tested_proposal("p1", actor="owner:test")
