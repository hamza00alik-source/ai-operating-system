import os
import pytest
from fastapi.testclient import TestClient

from ai_os.api import app
from ai_os.cinecode import initialize_cinecode
from ai_os.db import initialize_database, connect


@pytest.mark.skipif(not os.getenv("AI_OS_TEST_POSTGRES_URL"), reason="PostgreSQL CI service is not configured")
def test_cinecode_queue_works_with_postgres_adapter(monkeypatch):
    monkeypatch.setenv("AI_OS_ENV", "production")
    monkeypatch.setenv("AI_OS_API_KEY", "postgres-cinecode-test-key")
    monkeypatch.setenv("AI_OS_DATABASE_URL", os.environ["AI_OS_TEST_POSTGRES_URL"])
    initialize_database()
    initialize_cinecode()

    with TestClient(app) as client:
        created = client.post(
            "/cinecode/jobs",
            headers={"X-API-Key": "postgres-cinecode-test-key"},
            json={
                "brief": "Render a short film about a lighthouse during a winter storm.",
                "mode": "quick",
                "music_source": "none",
            },
        )
        assert created.status_code == 201
        job_id = created.json()["id"]
        approved = client.post(
            f"/cinecode/jobs/{job_id}/approve",
            headers={"X-API-Key": "postgres-cinecode-test-key"},
            json={},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

    with connect() as db:
        db.execute("DELETE FROM cinecode_jobs WHERE id=?", (job_id,))
