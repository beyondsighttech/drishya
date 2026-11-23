import tempfile
import json
import unittest
import zipfile
from pathlib import Path
import tests
from tools.build import build_package
from drishya.assets import write_inventory


class BuildTests(unittest.TestCase):
    def test_release_downloads_only_smol_and_its_runtime(self):
        lock = json.loads((tests.ROOT / "runtime-lock.json").read_text())
        self.assertEqual(len(lock["assets"]), 3)
        self.assertFalse(any("mirage" in a["name"].lower() or "python" in a["name"].lower()
                             or "cactus" in a["name"].lower() for a in lock["assets"]))
        self.assertLess(sum(a["size"] for a in lock["assets"]), 1_000_000_000)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "addon"
        plugin = self.source / "globalPlugins/drishya"
        plugin.mkdir(parents=True)
        (plugin / "__init__.py").write_text("# plugin")
        (plugin / "junk.pyc").write_bytes(b"junk")
        (self.source / "manifest.ini").write_text("name = drishya\nversion = 0.1.0")

    def test_slim_package_has_manifest_at_root_and_no_bytecode(self):
        path = build_package(self.root / "dist", False, None, self.source)
        with zipfile.ZipFile(path) as archive:
            self.assertIn("manifest.ini", archive.namelist())
            self.assertIn("globalPlugins/drishya/__init__.py", archive.namelist())
            self.assertFalse(any(name.endswith(".pyc") for name in archive.namelist()))

    def test_full_package_contains_verified_runtime(self):
        runtime = self.root / "runtime"
        runtime.mkdir()
        (runtime / "model.bin").write_bytes(b"model")
        write_inventory(runtime)
        path = build_package(self.root / "dist", True, runtime, self.source)
        with zipfile.ZipFile(path) as archive:
            self.assertIn("globalPlugins/drishya/runtime/inventory.json", archive.namelist())

    def test_corrupt_runtime_cannot_be_packaged(self):
        runtime = self.root / "runtime"
        runtime.mkdir()
        (runtime / "model.bin").write_bytes(b"model")
        write_inventory(runtime)
        (runtime / "model.bin").write_bytes(b"bad")
        with self.assertRaises(ValueError):
            build_package(self.root / "dist", True, runtime, self.source)
