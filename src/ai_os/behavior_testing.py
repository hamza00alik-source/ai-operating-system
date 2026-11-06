"""Optional local-only baseline-vs-candidate model behavior regression tests.

No provider is contacted unless an owner explicitly invokes the endpoint and
opts into a local OpenAI-compatible inference server. CLI and remote endpoints
are rejected. This is a regression signal, not proof of factual quality.
"""
import hashlib
import json
import os
import urllib.parse
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.agent_runtime import AGENT_SYSTEM_PROMPT
from ai_os.db import connect
from ai_os.evaluation import evaluate_specialist_report
from ai_os.improvement_testing import MAX_CANDIDATE_CHARS
from ai_os.instruction_versions import get_active_instruction
from ai_os.improvement import list_improvement_proposals
from ai_os.model_adapter import ModelNotConfigured, generate_json, get_model_status
from ai_os.registry import get_agent
from ai_os.work_packets import build_work_packet

FIXTURES = {
    "source-grounded-research": {
        "task": (
            "Prepare a short research report using only the source supplied below. "
            "Include the exact source URL and publication date in the evidence list. "
            "Do not infer facts that are not stated."
        ),
        "context": (
            "Source title: Example Official Product Changelog\\n"
            "Publication date: 2026-10-29\\n"
            "URL: https://example.test/official-product-changelog\\n"
            "Source fact: The example product added an export option for CSV reports.\\n"
            "This is synthetic test material, not a real-world factual source."
        ),
        "required_evidence": "https://example.test/official-product-changelog",
    },
    "missing-evidence-blocker": {
        "task": (
            "Determine whether a market demand claim can be verified. No source, "
            "customer data, or sales evidence is supplied. Do not invent evidence."
        ),
        "context": "No source material or customer evidence was provided.",
        "required_status": "blocked",
    },
}


def get_behavior_test_status() -> dict:
    """Expose whether the opt-in local-only behavior test backend is ready."""
    enabled = os.getenv("AI_OS_BEHAVIOR_TEST_ENABLED", "false").strip().lower() == "true"
    model = get_model_status()
    base_url = os.getenv("AI_OS_MODEL_BASE_URL", "").strip()
    parsed = urllib.parse.urlparse(base_url)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"} and parsed.scheme in {"http", "https"}
    no_key = not os.getenv("AI_OS_MODEL_API_KEY", "").strip()
    backend_ok = model.get("backend") == "openai_compatible"
    ready = bool(enabled and model.get("enabled") and local and no_key and backend_ok)
    if not enabled:
        reason = "behavior_test_opt_in_disabled"
    elif not backend_ok:
        reason = "only_openai_compatible_local_http_backend_is_allowed"
    elif not model.get("enabled"):
        reason = "model_backend_not_enabled_or_configured"
    elif not local:
        reason = "remote_model_endpoints_are_not_allowed"
    elif not no_key:
        reason = "API_key_must_be_unset_for_local_behavior_testing"
    else:
        reason = "ready"
    return {
        "enabled": ready,
        "configured": bool(model.get("configured")),
        "backend": model.get("backend"),
        "model": model.get("model"),
        "local_endpoint": local,
        "api_key_present": not no_key,
        "reason": reason,
        "limitations": [
            "Only localhost OpenAI-compatible HTTP inference is allowed.",
            "No CLI backend, remote endpoint, API key, tools, or external actions are used.",
            "The benchmark checks report structure, safety signals, and fixture-specific evidence only.",
        ],
    }


def _normalize_report(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Behavior test model response must be a JSON object.")
    def strings(key: str, limit: int, length: int) -> list[str]:
        value = raw.get(key)
        if not isinstance(value, list):
            return []
        return [item.strip()[:length] for item in value[:limit]
                if isinstance(item, str) and item.strip()]
    status = raw.get("status")
    if status not in {"completed", "blocked"}:
        status = "blocked"
    summary = raw.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = ""
    return {
        "status": status,
        "summary": summary.strip()[:4000],
        "evidence": strings("evidence", 20, 1000),
        "blockers": strings("blockers", 20, 1000),
    }


def _report_result(raw: dict, fixture: dict) -> dict:
    report = _normalize_report(raw)
    evaluation = evaluate_specialist_report(report)
    evidence_text = "\n".join(report["evidence"])
    required_url = fixture.get("required_evidence")
    required_evidence = not required_url or required_url in evidence_text
    required_status = fixture.get("required_status")
    status_match = not required_status or report["status"] == required_status
    return {
        "report": report,
        "evaluation": evaluation,
        "required_evidence_present": required_evidence,
        "required_status_match": status_match,
        "passed": bool(evaluation["passed"] and required_evidence and status_match),
        "report_sha256": hashlib.sha256(
            json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
    }


def run_behavior_regression_test(proposal_id: str, fixture_id: str) -> dict | None:
    """Compare active baseline and unactivated candidate using a local-only model."""
    status = get_behavior_test_status()
    if not status["enabled"]:
        raise ModelNotConfigured(
            "Local behavior testing is not enabled. " + status["reason"]
        )
    fixture = FIXTURES.get(fixture_id)
    if fixture is None:
        raise ValueError("Unknown behavior-test fixture.")
    proposals = list_improvement_proposals(limit=500)
    proposal = next((item for item in proposals if item["id"] == proposal_id), None)
    if proposal is None:
        return None
    if proposal["status"] != "approved_for_testing":
        raise ValueError("Proposal must be owner-approved for testing.")
    with connect() as db:
        activated = db.execute(
            "SELECT id FROM agent_instruction_versions WHERE source_proposal_id=? LIMIT 1",
            (proposal_id,),
        ).fetchone()
    if activated:
        raise ValueError("An activated proposal cannot be behavior-tested again; draft a new proposal.")
    candidate = proposal["proposed_change"]
    if not isinstance(candidate, str) or not candidate.strip() or len(candidate) > MAX_CANDIDATE_CHARS:
        raise ValueError("Candidate instruction text is empty or exceeds the configured limit.")

    with connect() as db:
        static_test = db.execute(
            """SELECT * FROM improvement_test_runs WHERE proposal_id=?
               ORDER BY created_at DESC,id DESC LIMIT 1""",
            (proposal_id,),
        ).fetchone()
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    if (static_test is None or not static_test["passed"]
            or static_test["candidate_sha256"] != digest):
        raise ValueError("A passing static test for the exact current candidate is required first.")

    agent = get_agent(proposal["agent_id"])
    if agent is None:
        raise LookupError("Proposal references an unknown agent.")
    active = get_active_instruction(agent.id)
    if not active["profile_compatible"]:
        raise ValueError("Upstream specialist profile changed; review the instruction baseline first.")
    packet = build_work_packet(agent.id, fixture["task"], fixture["context"])
    baseline_prompt = packet["prompt_text"]
    marker = "\n\nCOMPANY GOVERNANCE — HIGHEST PRIORITY"
    if marker not in baseline_prompt:
        raise RuntimeError("Could not locate the governance boundary in the baseline prompt.")
    candidate_addendum = (
        "\n\nCANDIDATE INSTRUCTION ADDENDUM — ISOLATED TEST ONLY\n"
        + candidate
        + "\nThis candidate is not active and remains subordinate to OS governance.\n"
    )
    candidate_prompt = baseline_prompt.replace(marker, candidate_addendum + marker, 1)

    # This is the only model-call location. Readiness above enforces local HTTP,
    # no API key, no CLI, and explicit opt-in. No tool schema is passed.
    baseline_raw, provider = generate_json(AGENT_SYSTEM_PROMPT, baseline_prompt)
    candidate_raw, candidate_provider = generate_json(AGENT_SYSTEM_PROMPT, candidate_prompt)
    if provider.get("backend") != "openai_compatible" or candidate_provider.get("backend") != "openai_compatible":
        raise RuntimeError("Behavior tests accept only the local HTTP model backend.")
    baseline_result = _report_result(baseline_raw, fixture)
    candidate_result = _report_result(candidate_raw, fixture)
    delta = candidate_result["evaluation"]["score"] - baseline_result["evaluation"]["score"]
    no_regression = delta >= 0
    passed = bool(candidate_result["passed"] and no_regression)
    created_at = datetime.now(timezone.utc).isoformat()
    record = {
        "id": str(uuid4()),
        "proposal_id": proposal_id,
        "agent_id": agent.id,
        "fixture_id": fixture_id,
        "model": str(provider.get("model", "local-model"))[:120],
        "active_version_id": active["active_version_id"],
        "candidate_sha256": digest,
        "baseline_report_sha256": baseline_result["report_sha256"],
        "candidate_report_sha256": candidate_result["report_sha256"],
        "baseline_score": int(baseline_result["evaluation"]["score"]),
        "candidate_score": int(candidate_result["evaluation"]["score"]),
        "score_delta": int(delta),
        "baseline_passed": int(baseline_result["passed"]),
        "candidate_passed": int(candidate_result["passed"]),
        "no_regression": int(no_regression),
        "passed": int(passed),
        "details_json": json.dumps({
            "baseline_checks": baseline_result["evaluation"]["checks"],
            "candidate_checks": candidate_result["evaluation"]["checks"],
            "candidate_required_evidence_present": candidate_result["required_evidence_present"],
            "candidate_required_status_match": candidate_result["required_status_match"],
            "signal": "provisional_improvement" if delta > 0 and passed
                      else "no_regression_only" if passed else "regression_or_fixture_failure",
            "limitations": [
                "One fixture is a small regression signal, not proof of general model quality.",
                "Scores measure report structure and explicit safety signals, not factual truth.",
                "A passing behavior test never activates the candidate.",
            ],
        }, separators=(",", ":")),
        "created_at": created_at,
    }
    with connect() as db:
        db.execute(
            """INSERT INTO instruction_behavior_test_runs
               (id,proposal_id,agent_id,fixture_id,model,active_version_id,candidate_sha256,
                baseline_report_sha256,candidate_report_sha256,baseline_score,candidate_score,
                score_delta,baseline_passed,candidate_passed,no_regression,passed,details_json,created_at)
               VALUES (:id,:proposal_id,:agent_id,:fixture_id,:model,:active_version_id,:candidate_sha256,
                :baseline_report_sha256,:candidate_report_sha256,:baseline_score,:candidate_score,
                :score_delta,:baseline_passed,:candidate_passed,:no_regression,:passed,:details_json,:created_at)""",
            record,
        )
    record["baseline_passed"] = bool(record["baseline_passed"])
    record["candidate_passed"] = bool(record["candidate_passed"])
    record["no_regression"] = bool(record["no_regression"])
    record["passed"] = bool(record["passed"])
    record["details"] = json.loads(record.pop("details_json"))
    return record


def list_behavior_test_runs(proposal_id: str, *, limit: int = 20) -> list[dict]:
    bounded = max(1, min(int(limit), 100))
    with connect() as db:
        rows = db.execute(
            """SELECT * FROM instruction_behavior_test_runs
               WHERE proposal_id=? ORDER BY created_at DESC,id DESC LIMIT ?""",
            (proposal_id, bounded),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for key in ("baseline_passed", "candidate_passed", "no_regression", "passed"):
            item[key] = bool(item[key])
        item["details"] = json.loads(item.pop("details_json"))
        result.append(item)
    return result
