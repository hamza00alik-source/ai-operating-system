import sqlite3
import unittest
from opencompany.queue import ExecutionQueue


class ExecutionQueueTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.queue = ExecutionQueue(self.db)

    def tearDown(self):
        self.db.close()

    def test_enqueue_is_idempotent_per_task(self):
        a = self.queue.enqueue("task-1", {"x": 1})
        b = self.queue.enqueue("task-1", {"x": 2})
        self.assertEqual(a, b)
        self.assertEqual(len(self.queue.list()), 1)

    def test_list_by_task_returns_task_execution_history(self):
        first = self.queue.enqueue("history-task", {"version": 1})
        second_task = self.queue.enqueue("other-task", {})
        self.assertEqual(self.queue.list_by_task("history-task"), [self.queue.get(first)])
        self.assertEqual(self.queue.list_by_task("other-task"), [self.queue.get(second_task)])
        self.assertEqual(self.queue.list_by_task("missing-task"), [])
        with self.assertRaises(ValueError):
            self.queue.list_by_task("")

    def test_claim_complete_and_worker_ownership(self):
        job = self.queue.enqueue("task-2", {"work": "draft"})
        claimed = self.queue.claim("worker-a")
        self.assertEqual(claimed["id"], job)
        self.assertIsNone(self.queue.claim("worker-b"))
        self.assertFalse(self.queue.complete(job, "worker-b", {"ok": True}, claimed["attempts"]))
        self.assertTrue(self.queue.heartbeat(job, "worker-a", claimed["attempts"]))
        self.assertTrue(self.queue.complete(job, "worker-a", {"ok": True}, claimed["attempts"]))
        self.assertEqual(self.queue.get(job)["state"], "completed")

    def test_failure_retries_then_dead_letters(self):
        job = self.queue.enqueue("task-3", {}, max_attempts=2)
        self.assertEqual(self.queue.claim("worker-a")["attempts"], 1)
        self.assertTrue(self.queue.fail(job, "worker-a", "temporary", 1))
        self.assertEqual(self.queue.claim("worker-b")["attempts"], 2)
        self.assertTrue(self.queue.fail(job, "worker-b", "permanent", 2))
        self.assertEqual(self.queue.get(job)["state"], "dead")


    def test_old_attempt_cannot_acknowledge_reclaimed_lease_with_same_worker_id(self):
        from datetime import datetime, timedelta, timezone

        job = self.queue.enqueue("task-stale-attempt", {}, max_attempts=3)
        first = self.queue.claim("reused-worker-id", lease_seconds=60)
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.db.execute(
            "UPDATE execution_jobs SET lease_until=? WHERE id=?",
            (expired, job),
        )
        self.db.commit()

        second = self.queue.claim("reused-worker-id", lease_seconds=60)
        self.assertEqual(second["attempts"], first["attempts"] + 1)
        self.assertFalse(self.queue.complete(
            job, "reused-worker-id", {"stale": True}, first["attempts"]
        ))
        self.assertFalse(self.queue.fail(
            job, "reused-worker-id", "stale failure", first["attempts"]
        ))
        self.assertTrue(self.queue.complete(
            job, "reused-worker-id", {"current": True}, second["attempts"]
        ))
        self.assertEqual(self.queue.get(job)["state"], "completed")

    def test_expired_lease_cannot_heartbeat_complete_or_fail(self):
        from datetime import datetime, timedelta, timezone

        job = self.queue.enqueue("task-expired-lease", {}, max_attempts=3)
        claimed = self.queue.claim("worker-old", lease_seconds=60)
        self.assertEqual(claimed["id"], job)
        expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.db.execute(
            "UPDATE execution_jobs SET lease_until=? WHERE id=?",
            (expired, job),
        )
        self.db.commit()

        self.assertFalse(self.queue.heartbeat(job, "worker-old", claimed["attempts"]))
        self.assertFalse(self.queue.complete(job, "worker-old", {"ok": True}, claimed["attempts"]))
        self.assertFalse(self.queue.fail(job, "worker-old", "late failure", claimed["attempts"]))
        self.assertEqual(self.queue.get(job)["state"], "leased")

        reclaimed = self.queue.claim("worker-new", lease_seconds=60)
        self.assertEqual(reclaimed["id"], job)
        self.assertEqual(reclaimed["attempts"], 2)
        self.assertTrue(self.queue.complete(job, "worker-new", {"ok": True}, reclaimed["attempts"]))


if __name__ == "__main__":
    unittest.main()
