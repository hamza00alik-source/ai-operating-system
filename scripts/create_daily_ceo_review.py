"""Create one idempotent daily internal CEO review plan.

This schedules review of existing company records and learning signals. It does
not perform web search or assert that external research has been conducted.
"""
import json
from datetime import datetime, timezone

from ai_os.ceo_brain import create_ceo_plan
from ai_os.ceo_schemas import CEOObjectiveCreate
from ai_os.db import connect
from ai_os.agent_runtime import schedule_ready_steps


def main() -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    objective = (
        f"Daily internal operations and learning review for {today}: review active "
        "company runs, blocked steps, recent specialist evaluations, accepted company "
        "knowledge, open improvement proposals, and unresolved delivery risks. "
        "Prepare a prioritized CEO coordination report with evidence, owners, and "
        "next steps. Do not claim external web research or customer activity."
    )
    with connect() as db:
        existing = db.execute(
            "SELECT run_id FROM ceo_plan_metadata WHERE objective=? LIMIT 1",
            (objective,),
        ).fetchone()
    if existing:
        print(json.dumps({
            "status": "already_created",
            "date": today,
            "run_id": existing["run_id"],
            "model_execution": "not_requested",
        }))
        return

    plan = create_ceo_plan(CEOObjectiveCreate(
        objective=objective,
        context=(
            "Daily cadence: inspect only records already stored in this AI Operating "
            "System. Identify stale runs, repeated evaluation failures, missing evidence, "
            "and candidate improvements. All findings must be traceable to persisted "
            "run IDs, evaluation records, or accepted knowledge. External actions remain "
            "disabled and owner approval remains mandatory."
        ),
    ))
    scheduled = schedule_ready_steps()
    print(json.dumps({
        "status": "created",
        "date": today,
        "run_id": plan["run_id"],
        "scheduled_steps": scheduled.get("scheduled", 0),
        "model_enabled": scheduled.get("model_enabled", False),
        "limitations": plan["limitations"],
    }, indent=2))


if __name__ == "__main__":
    main()
