from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from ai_os.db import initialize_database
from ai_os.schemas import ApprovalCreate, ApprovalDecision
from ai_os.service import create_approval, decide_approval


def test_concurrent_decisions_consume_approval_once(monkeypatch, tmp_path):
    database = tmp_path / "approval-test.db"
    monkeypatch.setenv("AI_OS_DATABASE_URL", f"sqlite:///{database}")
    initialize_database()
    approval = create_approval(ApprovalCreate(action="publish_content"))
    barrier = Barrier(2)

    def decide(value):
        barrier.wait()
        try:
            decide_approval(
                approval["id"], ApprovalDecision(decision=value)
            )
            return "success"
        except ValueError:
            return "already_decided"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(decide, ("approved", "rejected")))

    assert outcomes.count("success") == 1
    assert outcomes.count("already_decided") == 1
