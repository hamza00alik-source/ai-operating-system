"""Isolated, deterministic screening for proposed agent-instruction changes.

This is a text/policy contract check, not an LLM behavior benchmark. It never
loads or changes live agent profiles and never activates a candidate.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect

BASELINE_POLICY_VERSION = "company-agent-policy-v1"
MAX_CANDIDATE_CHARS = 4000
_UNSAFE_PATTERNS = {
    "instruction_override": re.compile(
        r"ignore\s+(all\s+)?(previous|prior|system|developer)\s+instructions|"
        r"override\s+(the\s+)?(system|developer|owner)\s+(prompt|policy|approval)",
        re.IGNORECASE,
    ),
    "approval_bypass": re.compile(
        r"bypass\s+(owner|human|ceo)\s+approval|"
        r"without\s+(owner|human)\s+approval|"
        r"do\s+not\s+ask\s+the\s+owner",
        re.IGNORECASE,
    ),
    "unrestricted_execution": re.compile(
        r"unrestricted\s+(shell|tool|browser|network)|"
        r"disable\s+(all\s+)?(safety|security|guardrails)|"
        r"execute\s+any\s+command",
        re.IGNORECASE,
    ),
    "unauthorized_external_action": re.compile(
        r"(publish|send\s+(an?\s+)?(email|message)|charge|refund|spend)"
        r".{0,100}(automatically|without\s+approval|without\s+permission)",
        re.IGNORECASE | re.DOTALL,
    ),
}


def run_proposal_regression_tests(proposal_id: str) -> dict | None:
    """Screen an owner-approved proposal; store an immutable test-run record."""
    with connect() as db:
        proposal = db.execute(
            "SELECT * FROM improvement_proposals WHERE id=?", (proposal_id,)
        ).fetchone()
        if proposal is None:
            return None
        if proposal["status"] != "approved_for_testing":
            raise ValueError("Only owner-approved proposals can be tested.")
        candidate = proposal["proposed_change"]
        evidence = json.loads(proposal["evidence_json"])
        checks = [
            {"key": "candidate_text_present", "passed": bool(candidate.strip())},
            {"key": "candidate_text_within_limit", "passed": len(candidate) <= MAX_CANDIDATE_CHARS},
            {"key": "supporting_evidence_present", "passed": len(evidence) >= 2},
        ]
        for key, pattern in _UNSAFE_PATTERNS.items():
            checks.append({"key": key, "passed": pattern.search(candidate) is None})
        digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        passed = all(check["passed"] for check in checks)
        result = {
            "id": str(uuid4()),
            "proposal_id": proposal_id,
            "baseline_policy_version": BASELINE_POLICY_VERSION,
            "candidate_sha256": digest,
            "passed": passed,
            "checks_json": json.dumps(checks, separators=(",", ":")),
            "limitations_json": json.dumps([
                "Static text screening only; no model was invoked.",
                "Does not compare live agent prompts or measure model behavior.",
                "A passing result is not authorization to adopt or activate the candidate.",
            ], separators=(",", ":")),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        db.execute(
            """INSERT INTO improvement_test_runs
            (id,proposal_id,baseline_policy_version,candidate_sha256,passed,
             checks_json,limitations_json,created_at)
            VALUES (:id,:proposal_id,:baseline_policy_version,:candidate_sha256,
                    :passed,:checks_json,:limitations_json,:created_at)""",
            {**result, "passed": int(passed)},
        )
    return _decode_test_run(result)


def _decode_test_run(row) -> dict:
    item = dict(row)
    item["passed"] = bool(item["passed"])
    item["checks"] = json.loads(item.pop("checks_json"))
    item["limitations"] = json.loads(item.pop("limitations_json"))
    return item


def list_proposal_test_runs(proposal_id: str, *, limit: int = 20) -> list[dict]:
    bounded = max(1, min(int(limit), 100))
    with connect() as db:
        rows = db.execute(
            """SELECT * FROM improvement_test_runs
            WHERE proposal_id=? ORDER BY created_at DESC,id DESC LIMIT ?""",
            (proposal_id, bounded),
        ).fetchall()
    return [_decode_test_run(row) for row in rows]
