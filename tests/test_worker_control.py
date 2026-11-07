from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.worker_service import run_worker_loop


def test_owner_can_pause_resume_and_stop_persistent_worker():
    with TestClient(app) as client:
        initial = client.get("/worker/status")
        assert initial.status_code == 200
        assert initial.json()["desired_state"] in {"stopped", "paused", "running"}

        paused = client.post("/worker/pause")
        assert paused.status_code == 200
        assert paused.json()["desired_state"] == "paused"

        resumed = client.post("/worker/resume")
        assert resumed.status_code == 200
        assert resumed.json()["desired_state"] == "running"

        stopped = client.post("/worker/stop")
        assert stopped.status_code == 200
        assert stopped.json()["desired_state"] == "stopped"


def test_worker_loop_does_not_schedule_or_claim_jobs_while_paused():
    calls = {"schedule": 0, "run": 0, "heartbeat": []}
    sleeps = []
    stop = {"value": False}

    def sleep(_):
        stop["value"] = True

    def schedule():
        calls["schedule"] += 1
        return {"scheduled": 0}

    def run(*, worker_id):
        calls["run"] += 1
        return {"processed": False}

    def heartbeat(worker_id, status, current_job_id):
        calls["heartbeat"].append((status, current_job_id))

    run_worker_loop(
        worker_id="paused-test-worker",
        poll_seconds=1,
        stop_requested=lambda: stop["value"],
        sleep=sleep,
        schedule=schedule,
        run=run,
        desired_state=lambda: "paused",
        heartbeat=heartbeat,
    )

    assert calls["schedule"] == 0
    assert calls["run"] == 0
    assert [item[0] for item in calls["heartbeat"]] == ["starting", "paused"]


def test_worker_loop_respects_stopped_state_until_owner_starts_it():
    calls = {"schedule": 0, "run": 0}
    stop = {"value": False}
    states = iter(["stopped", "running"])

    def sleep(_):
        if calls["run"]:
            stop["value"] = True

    def schedule():
        calls["schedule"] += 1
        return {"scheduled": 0}

    def run(*, worker_id):
        calls["run"] += 1
        return {"processed": False}

    run_worker_loop(
        worker_id="start-test-worker",
        poll_seconds=1,
        stop_requested=lambda: stop["value"],
        sleep=sleep,
        schedule=schedule,
        run=run,
        desired_state=lambda: next(states),
    )

    assert calls["schedule"] == 1
    assert calls["run"] == 1



def test_dashboard_exposes_worker_controls_and_live_status():
    with TestClient(app) as client:
        response = client.get("/dashboard")
    assert response.status_code == 200
    assert 'id="workerControl"' in response.text
    assert 'id="workerState"' in response.text
    assert 'data-worker-action="pause"' in response.text
    assert 'async function controlWorker(action)' in response.text
