"""Optional integration tests with the real pinned native runtimes."""
import os
import threading
import unittest
from pathlib import Path
import tests
from drishya.engine import Engine


@unittest.skipUnless(os.environ.get("DRISHYA_LIVE_MODELS"), "Set DRISHYA_LIVE_MODELS=1 to run real models")
class RuntimeTests(unittest.TestCase):
    def test_smol_describes_fixture_using_owned_tcp_peer(self):
        from qa.benchmark import image_data
        engine = Engine(tests.ROOT / "build/runtime")
        self.addCleanup(engine.close)
        result = engine.describe(image_data(tests.ROOT / "qa/artifacts/photo-library.png"),
                                 "concise", 4, threading.Event())
        self.assertTrue(result.text.strip())
        self.assertLessEqual(len(result.text.split()), 90)
        process = engine.process
        engine.close()
        self.assertIsNotNone(process.poll())
