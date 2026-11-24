import sqlite3
import unittest
from opencompany.queue import ExecutionQueue
from opencompany.worker import Worker


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.queue = ExecutionQueue(self.db)

    def tearDown(self):
        self.db.close()

    def test_dispatches_registered_handler(self):
        job = self.queue.enqueue("task-worker-1", {
            "handler": "echo", "input": {"message": "hello"}
        })
        worker = Worker(self.queue, "worker-1", {
            "echo": lambda data: {"echo": data["message"]}
        })
        result = worker.run_once()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.queue.get(job)["state"], "completed")

    def test_unknown_handler_is_failed_and_requeued(self):
        job = self.queue.enqueue("task-worker-2", {"handler": "missing"}, max_attempts=2)
        worker = Worker(self.queue, "worker-1", {})
        result = worker.run_once()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.queue.get(job)["state"], "queued")


if __name__ == "__main__":
    unittest.main()
