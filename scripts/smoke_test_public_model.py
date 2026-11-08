"""Live end-to-end AIOS company workflow using the public no-key OVH model.

This intentionally sends a small test task to the public model. No credentials
or private customer data are included. The endpoint is rate-limited.
"""
import os
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="aios-live-smoke-") as temp_dir:
    os.environ["AI_OS_ENV"] = "development"
    os.environ["AI_OS_DATABASE_URL"] = f"sqlite:///{Path(temp_dir) / 'ai_os.db'}"
    os.environ["AI_OS_AGENT_SIGNING_KEY"] = "live-smoke-test-signing-key-" + "x" * 40
    os.environ["AI_OS_MODEL_ENABLED"] = "true"
    os.environ["AI_OS_MODEL_BACKEND"] = "openai_compatible"
    os.environ["AI_OS_MODEL_PROVIDER"] = "ovhcloud-anonymous"
    os.environ["AI_OS_MODEL_BASE_URL"] = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"
    os.environ["AI_OS_MODEL_NAME"] = "gpt-oss-20b"
    os.environ["AI_OS_MODEL_API_KEY"] = ""
    os.environ["AI_OS_FREE_ONLY"] = "true"
    os.environ["AI_OS_FREE_MODEL_ALLOWLIST"] = "gpt-oss-20b"
    os.environ["AI_OS_AUTO_CEO_REVIEW_ENABLED"] = "true"
    os.environ["AI_OS_MODEL_TIMEOUT_SECONDS"] = "60"

    from fastapi.testclient import TestClient
    from ai_os.api import app

    task = {
        "title": "AIOS live public-model integration check",
        "description": "A small synthetic test of the complete supervised workflow.",
        "steps": [
            {
                "step_key": "research",
                "agent_id": "product-trend-researcher",
                "task": (
                    "Identify two plausible buyer needs for a downloadable desktop "
                    "gaming utility. Clearly label any assumptions; do not claim live research."
                ),
            },
            {
                "step_key": "strategy",
                "agent_id": "business-strategist",
                "task": (
                    "Recommend one small downloadable product using the preceding "
                    "research report. State risks and validation steps."
                ),
                "depends_on": ["research"],
            },
        ],
    }

    try:
        with TestClient(app) as client:
            created = client.post("/company-runs", json=task)
            if created.status_code != 201:
                raise RuntimeError(f"Could not create test company run: HTTP {created.status_code}")
            run_id = created.json()["id"]
            expected_jobs = ["execute_company_step", "execute_company_step", "review_company_run"]
            completed_jobs = []
            for expected_type in expected_jobs:
                response = client.post("/worker/run-once")
                if response.status_code != 200:
                    raise RuntimeError(f"Worker returned HTTP {response.status_code}")
                result = response.json()
                job = result.get("job") or {}
                if job.get("status") != "completed" or job.get("job_type") != expected_type:
                    raise RuntimeError(
                        f"Expected completed {expected_type}; got "
                        f"{job.get('job_type')} / {job.get('status')}"
                    )
                completed_jobs.append(job)

            final = client.get(f"/company-runs/{run_id}")
            if final.status_code != 200:
                raise RuntimeError("Could not retrieve final company run")
            company_run = final.json()
            if company_run.get("status") != "completed":
                raise RuntimeError(f"Company run ended with status {company_run.get('status')}")
            if [step.get("status") for step in company_run.get("steps", [])] != [
                "completed", "completed"
            ]:
                raise RuntimeError("Both specialist steps did not complete")

            ceo_result = completed_jobs[-1].get("result") or {}
            if not ceo_result.get("summary"):
                raise RuntimeError("CEO review did not return a summary")

            print("PASS: live AIOS company workflow completed using the no-key public model.")
            print("Verified: Researcher -> dependent Strategist -> automatic CEO review.")
            print("Verified: durable queue, real model adapter, report handoff and final review.")
            print("No external store, customer, payment, publishing or deployment action was attempted.")
    except Exception as exc:
        raise SystemExit(
            f"Live AIOS public-model workflow failed: {type(exc).__name__}: {str(exc)[:300]}"
        ) from exc
