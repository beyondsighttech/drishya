import hashlib
import importlib.util
import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
import tests
from drishya.assets import download_asset, extract_archive, install_runtime, verify_runtime, runtime_location, Cancelled


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def asset(self, content=b"test data", name="model.bin"):
        source = self.root / ("source-" + name)
        source.write_bytes(content)
        return {"name": name, "url": source.as_uri(), "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "kind": "file", "destination": "models/" + name}

    def test_offline_recovery_keeps_original_runtime_location(self):
        package = self.root / "package"
        package.mkdir()
        (package / "runtime-previous").mkdir()
        self.assertEqual(runtime_location(package, self.root / "userdata"), package / "runtime")

    def test_partial_bundled_runtime_is_repaired_in_place(self):
        package = self.root / "package"
        (package / "runtime").mkdir(parents=True)
        self.assertEqual(runtime_location(package, self.root / "userdata"), package / "runtime")

    def test_download_integrity(self):
        asset = self.asset()
        target = download_asset(asset, self.root / "cache", threading.Event())
        self.assertEqual(target.read_bytes(), b"test data")

    def test_corrupt_download_not_published(self):
        asset = self.asset()
        asset["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            download_asset(asset, self.root / "cache", threading.Event())
        self.assertFalse((self.root / "cache" / asset["name"]).exists())

    def test_cancelled_download(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(Cancelled):
            download_asset(self.asset(), self.root / "cache", event)

    def test_zip_traversal_and_windows_paths_rejected(self):
        for name in ["../escape", "C:/escape", "folder/../../escape", "folder\\..\\escape", "folder/file:stream"]:
            data = io.BytesIO()
            with zipfile.ZipFile(data, "w") as archive:
                archive.writestr(name, b"oops")
            data.seek(0)
            with self.assertRaises(ValueError):
                extract_archive(data, self.root / "expanded", threading.Event())

    def test_incomplete_setup_does_not_destroy_previous_runtime(self):
        runtime = self.root / "runtime"
        runtime.mkdir()
        (runtime / "previous").write_text("keep")
        asset = self.asset()
        asset["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            install_runtime({"assets": [asset]}, runtime, self.root / "cache", threading.Event())
        self.assertEqual((runtime / "previous").read_text(), "keep")

    def test_installed_inventory_detects_tampering(self):
        runtime = self.root / "runtime"
        install_runtime({"assets": [self.asset()]}, runtime, self.root / "cache", threading.Event())
        self.assertTrue(verify_runtime(runtime))
        (runtime / "models" / "model.bin").write_bytes(b"bad")
        with self.assertRaises(ValueError):
            verify_runtime(runtime)

    def test_budget_enforced_before_download(self):
        asset = self.asset()
        asset["size"] = 1_000_000_001
        with self.assertRaises(ValueError):
            install_runtime({"assets": [asset]}, self.root / "runtime", self.root / "cache", threading.Event())

    def test_inventory_paths_cannot_escape(self):
        runtime = self.root / "runtime"
        runtime.mkdir()
        (runtime / "inventory.json").write_text(json.dumps({"files": [{"path": "../outside", "size": 0, "sha256": "0" * 64}]}))
        with self.assertRaises(ValueError):
            verify_runtime(runtime)

    def test_reloaded_module_cannot_install_over_active_setup(self):
        import drishya.assets as original
        spec = importlib.util.spec_from_file_location("reloaded_assets", original.__file__)
        reloaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reloaded)
        entered, release = threading.Event(), threading.Event()
        actual_download = original.download_asset
        failures = []

        def delayed(*args, **kwargs):
            entered.set()
            release.wait(2)
            return actual_download(*args, **kwargs)

        lock = {"assets": [self.asset()]}
        def install():
            try:
                original.install_runtime(lock, self.root / "runtime", self.root / "cache", threading.Event())
            except Exception as error:
                failures.append(error)

        from unittest.mock import patch
        with patch.object(original, "download_asset", delayed):
            worker = threading.Thread(target=install)
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                with self.assertRaises(ValueError):
                    reloaded.install_runtime(lock, self.root / "runtime", self.root / "cache", threading.Event())
            finally:
                release.set()
                worker.join(3)
        self.assertEqual(failures, [])

    def test_setup_recovers_verified_previous_runtime_after_interruption(self):
        from drishya.assets import write_inventory
        backup = self.root / "runtime-previous"
        backup.mkdir()
        (backup / "old.bin").write_bytes(b"previous model")
        write_inventory(backup)
        install_runtime({"assets": [self.asset()]}, self.root / "runtime", self.root / "cache", threading.Event())
        self.assertTrue(verify_runtime(self.root / "runtime"))
        self.assertFalse(backup.exists())

    def test_abandoned_generated_stage_is_cleaned(self):
        abandoned = self.root / "runtime-staging-abcdefgh"
        abandoned.mkdir()
        (abandoned / "partial-model").write_bytes(b"partial")
        unrelated = self.root / "runtime-staging-user-notes"
        unrelated.mkdir()
        install_runtime({"assets": [self.asset()]}, self.root / "runtime", self.root / "cache", threading.Event())
        self.assertFalse(abandoned.exists())
        self.assertTrue(unrelated.exists())

    def test_cache_cleanup_preserves_unrelated_files(self):
        cache = self.root / "cache"
        cache.mkdir()
        (cache / "notes.txt").write_text("keep")
        asset = self.asset()
        install_runtime({"assets": [asset]}, self.root / "runtime", cache, threading.Event(), cleanup_cache=True)
        self.assertFalse((cache / asset["name"]).exists())
        self.assertEqual((cache / "notes.txt").read_text(), "keep")

    def test_cache_cleanup_is_inside_cross_reload_lock(self):
        import drishya.assets as original
        spec = importlib.util.spec_from_file_location("reloaded_cleanup_assets", original.__file__)
        reloaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reloaded)
        entered, release = threading.Event(), threading.Event()
        failures = []
        lock = {"assets": [self.asset()]}

        def delayed_cleanup(*args):
            entered.set()
            release.wait(2)

        def install():
            try:
                original.install_runtime(lock, self.root / "runtime", self.root / "cache", threading.Event(), cleanup_cache=True)
            except Exception as error:
                failures.append(error)

        from unittest.mock import patch
        with patch.object(original, "cleanup_download_cache", delayed_cleanup, create=True):
            worker = threading.Thread(target=install)
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                with self.assertRaises(ValueError):
                    reloaded.install_runtime(lock, self.root / "runtime", self.root / "cache", threading.Event())
            finally:
                release.set()
                worker.join(3)
        self.assertEqual(failures, [])
