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

    def test_claim_complete_and_worker_ownership(self):
        job = self.queue.enqueue("task-2", {"work": "draft"})
        claimed = self.queue.claim("worker-a")
        self.assertEqual(claimed["id"], job)
        self.assertIsNone(self.queue.claim("worker-b"))
        self.assertFalse(self.queue.complete(job, "worker-b", {"ok": True}))
        self.assertTrue(self.queue.heartbeat(job, "worker-a"))
        self.assertTrue(self.queue.complete(job, "worker-a", {"ok": True}))
        self.assertEqual(self.queue.get(job)["state"], "completed")

    def test_expired_lease_cannot_complete(self):
        job = self.queue.enqueue("task-expired", {})
        self.assertIsNotNone(self.queue.claim("worker-a"))
        self.db.execute(
            "UPDATE execution_jobs SET lease_until=? WHERE id=?",
            ("2000-01-01T00:00:00+00:00", job),
        )
        self.db.commit()
        self.assertFalse(self.queue.complete(job, "worker-a", {"ok": True}))
        self.assertEqual(self.queue.get(job)["state"], "leased")

    def test_failure_retries_then_dead_letters(self):
        job = self.queue.enqueue("task-3", {}, max_attempts=2)
        self.assertEqual(self.queue.claim("worker-a")["attempts"], 1)
        self.assertTrue(self.queue.fail(job, "worker-a", "temporary"))
        self.assertEqual(self.queue.claim("worker-b")["attempts"], 2)
        self.assertTrue(self.queue.fail(job, "worker-b", "permanent"))
        self.assertEqual(self.queue.get(job)["state"], "dead")


if __name__ == "__main__":
    unittest.main()
