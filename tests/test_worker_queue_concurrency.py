"""Concurrency regression tests for SQLite-backed worker claims.

These exercise independent SQLite connections, the same topology used by
separate worker processes on one host. They do not claim multi-host guarantees.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest

from opencompany_core.worker_queue import DurableWorkerQueue, QueueError


def test_independent_queue_connections_never_issue_duplicate_live_claims(tmp_path):
    database = tmp_path / "competing-claims.sqlite3"
    agent_id, work_item_id = uuid4(), uuid4()
    setup = DurableWorkerQueue(database, lease_seconds=30)
    setup.enqueue(work_item_id, agent_id, {"kind": "internal_draft"})
    setup.close()

    queues = [
        DurableWorkerQueue(database, lease_seconds=30),
        DurableWorkerQueue(database, lease_seconds=30),
    ]
    barrier = Barrier(2)
    instant = datetime.now(timezone.utc) + timedelta(seconds=30)

    def compete(queue):
        barrier.wait(timeout=5)
        return queue.claim(agent_id, now=instant)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(compete, queue) for queue in queues]
            results = [future.result(timeout=10) for future in futures]

        leases = [result for result in results if result is not None]
        assert len(leases) == 1
        assert leases[0].work_item_id == work_item_id
        assert leases[0].attempt == 1
        assert queues[0].counts() == {"leased": 1}
        assert len(queues[0].list_attempts(work_item_id)) == 1
        assert queues[0].list_attempts(work_item_id)[0]["status"] == "running"
    finally:
        for queue in queues:
            queue.close()


def test_expired_claim_is_fenced_from_checkpoint_after_reclaim(tmp_path):
    queue = DurableWorkerQueue(
        tmp_path / "checkpoint-fencing.sqlite3",
        lease_seconds=10,
        retry_base_seconds=1,
        retry_max_seconds=1,
    )
    work_item_id, agent_id = uuid4(), uuid4()
    start = datetime.now(timezone.utc) + timedelta(seconds=30)
    queue.enqueue(work_item_id, agent_id, {})
    first = queue.claim(agent_id, now=start)
    assert first is not None

    expired = start + timedelta(seconds=11)
    assert queue.claim(agent_id, now=expired) is None
    replacement = queue.claim(agent_id, now=expired + timedelta(seconds=1))
    assert replacement is not None and replacement.attempt == 2

    assert queue.save_checkpoint(
        first, "market_intelligence_analyst", "specialist_output", {"content": "stale"}
    ) is False
    assert queue.save_checkpoint(
        replacement, "market_intelligence_analyst", "specialist_output",
        {"content": "current"},
    ) is True
    assert queue.get_checkpoint(
        work_item_id, "market_intelligence_analyst", "specialist_output"
    )["payload"]["content"] == "current"
    with pytest.raises(QueueError):
        queue.complete(first)
    queue.complete(replacement)
    queue.close()


def test_concurrent_claims_across_many_items_have_one_lease_per_item(tmp_path):
    database = tmp_path / "claim-batch.sqlite3"
    agent_id = uuid4()
    work_item_ids = [uuid4() for _ in range(8)]
    setup = DurableWorkerQueue(database, lease_seconds=30)
    for work_item_id in work_item_ids:
        setup.enqueue(work_item_id, agent_id, {})
    setup.close()

    queues = [DurableWorkerQueue(database, lease_seconds=30) for _ in range(8)]
    barrier = Barrier(len(queues))
    instant = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)

    def claim_one(queue):
        barrier.wait(timeout=5)
        return queue.claim(agent_id, now=instant)

    try:
        with ThreadPoolExecutor(max_workers=len(queues)) as pool:
            futures = [pool.submit(claim_one, queue) for queue in queues]
            results = [future.result(timeout=15) for future in futures]
        leases = [result for result in results if result is not None]
        assert len(leases) == len(queues)
        assert len({lease.work_item_id for lease in leases}) == len(queues)
        assert len({lease.lease_token for lease in leases}) == len(queues)
        assert all(lease.attempt == 1 for lease in leases)
        assert queues[0].counts() == {"leased": len(queues)}
        for lease in leases:
            queues[0].complete(lease)
        assert queues[0].counts() == {"done": len(queues)}
    finally:
        for queue in queues:
            queue.close()
