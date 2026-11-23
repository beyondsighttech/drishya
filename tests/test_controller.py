import threading
import time
import unittest
import tests
from drishya.controller import JobController


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.pending = []
        self.success = []
        self.errors = []
        self.controller = JobController(self.pending.append)
        self.addCleanup(self.controller.close)

    def pump(self):
        deadline = time.monotonic() + 1
        while not self.pending and time.monotonic() < deadline:
            time.sleep(.01)
        for callback in self.pending[:]:
            callback()
        self.pending.clear()

    def test_result_is_delivered_on_dispatcher(self):
        self.controller.start(lambda cancel: "result", self.success.append, self.errors.append)
        self.pump()
        self.assertEqual(self.success, ["result"])
        self.assertFalse(self.controller.busy)

    def test_cancel_discards_late_queued_result(self):
        self.controller.start(lambda cancel: "old result", self.success.append, self.errors.append)
        time.sleep(.02)
        self.controller.cancel()
        self.pump()
        self.assertEqual(self.success, [])

    def test_closed_controller_cannot_deliver_or_start(self):
        self.controller.start(lambda cancel: "old result", self.success.append, self.errors.append)
        self.controller.close()
        self.pump()
        self.assertEqual(self.success, [])
        with self.assertRaises(RuntimeError):
            self.controller.start(lambda cancel: "x", self.success.append, self.errors.append)

    def test_error_delivered_once(self):
        def fail(cancel):
            raise ValueError("No visible image")
        self.controller.start(fail, self.success.append, self.errors.append)
        self.pump()
        self.assertEqual(len(self.errors), 1)
        self.assertEqual(str(self.errors[0]), "No visible image")

    def test_cancel_sets_worker_event(self):
        observed = threading.Event()
        def work(cancel):
            if cancel.wait(1):
                observed.set()
            return "late"
        self.controller.start(work, self.success.append, self.errors.append)
        self.controller.cancel()
        self.assertTrue(observed.wait(.5))

    def test_running_cancelled_job_prevents_overlapping_setup(self):
        release = threading.Event()
        self.addCleanup(release.set)
        self.controller.start(lambda cancel: release.wait(1), self.success.append, self.errors.append)
        self.controller.cancel()
        self.assertTrue(self.controller.running)
        with self.assertRaises(RuntimeError):
            self.controller.start(lambda cancel: "overlap", self.success.append, self.errors.append)
