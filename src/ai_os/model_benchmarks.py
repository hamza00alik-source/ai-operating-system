"""Persistent ledger for explicitly owner-triggered model benchmarks.

No background work or inference is performed by this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ai_os.db import connect


def record_benchmark(*, provider: str, model: str | None, outcome: str,
                     latency_ms: int | None, usage: dict | None,
                     error: str | None, cost_class: str) -> dict:
    usage = usage if isinstance(usage, dict) else {}
    now = datetime.now(timezone.utc).isoformat()
    # Keep only non-sensitive diagnostic fields; never persist prompts or model output.
    safe_error = " ".join(str(error or "").split())[:500]
    row = {
        "id": str(uuid4()), "provider": str(provider)[:64],
        "model": str(model)[:200] if model is not None else None,
        "outcome": str(outcome)[:32],
        "latency_ms": max(0, int(latency_ms)) if latency_ms is not None else None,
        "input_tokens": _optional_int(usage.get("input_tokens")),
        "output_tokens": _optional_int(usage.get("output_tokens")),
        "total_tokens": _optional_int(usage.get("total_tokens")),
        "usage_reported": bool(usage.get("reported_by_provider")),
        "cost_class": str(cost_class)[:40],
        "error_summary": safe_error,
        "triggered_by": "owner_authenticated",
        "created_at": now,
    }
    with connect() as db:
        db.execute(
            """INSERT INTO model_benchmarks
               (id,provider,model,outcome,latency_ms,input_tokens,output_tokens,total_tokens,
                usage_reported,cost_class,error_summary,triggered_by,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row["id"], row["provider"], row["model"], row["outcome"], row["latency_ms"],
             row["input_tokens"], row["output_tokens"], row["total_tokens"],
             int(row["usage_reported"]), row["cost_class"], row["error_summary"],
             row["triggered_by"], row["created_at"]),
        )
    return row


def _optional_int(value):
    try:
        return max(0, int(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def list_benchmarks(limit: int = 50) -> list[dict]:
    limit = max(1, min(int(limit), 200))
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM model_benchmarks ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [
        {**dict(row), "usage_reported": bool(row["usage_reported"])}
        for row in rows
    ]
