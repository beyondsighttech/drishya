import sys
import types
from unittest.mock import patch
import unittest
import tests
from drishya.geometry import Rect
from drishya.settings import Options
from drishya.capture import Snapshot, capture_snapshot
from drishya.dialogs import ResultDialog, SettingsDialog


@unittest.skipUnless(sys.platform == "win32", "Native Windows wx test")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wx
        cls.wx = wx
        cls.app = wx.App.Get() or wx.App(False)

    def test_screen_curtain_blocks_capture_with_clear_message(self):
        curtain = types.SimpleNamespace(screenCurtain=types.SimpleNamespace(enabled=True))
        with patch.dict(sys.modules, {"screenCurtain": curtain}):
            with self.assertRaisesRegex(ValueError, "Please disable Screen Curtain"):
                capture_snapshot()

    def test_wgc_describes_behind_curtain_without_disabling_it(self):
        import drishya.capture as capture
        curtain = types.SimpleNamespace(screenCurtain=types.SimpleNamespace(enabled=True))
        image = self.wx.Image(4, 4)
        image.SetData(bytes([255, 0, 0]) * 16)
        with patch.dict(sys.modules, {"screenCurtain": curtain}), patch.object(capture, "capture_with_wgc", return_value=image, create=True), \
                patch.object(capture, "desktop_rect", return_value=Rect(0, 0, 4, 4), create=True):
            snapshot = capture_snapshot()
        self.assertEqual(bytes(snapshot.image.GetData())[:3], b"\xff\0\0")
        self.assertTrue(curtain.screenCurtain.enabled)

    def test_wgc_failure_with_curtain_does_not_fall_back_to_black_gdi(self):
        import drishya.capture as capture
        curtain = types.SimpleNamespace(screenCurtain=types.SimpleNamespace(enabled=True))
        with patch.dict(sys.modules, {"screenCurtain": curtain}), patch.object(capture, "capture_with_wgc", side_effect=RuntimeError("capture failed"), create=True):
            with self.assertRaisesRegex(ValueError, "Screen Curtain"):
                capture_snapshot()

    def test_crop_in_negative_desktop_coordinates(self):
        image = self.wx.Image(400, 200)
        image.SetData(bytes([255, 0, 0]) * 400 * 200)
        snapshot = Snapshot(image, Rect(-400, 0, 400, 200))
        result = snapshot.crop(Rect(-300, 0, 200, 100), 128)
        self.assertEqual((result.width, result.height), (128, 64))
        self.assertEqual(result.rgb[:3], b"\xff\0\0")
        self.assertTrue(result.png.startswith(b"\x89PNG"))

    def test_result_actions_have_native_accessible_labels(self):
        dialog = ResultDialog(None, "Current focus", lambda: None, lambda: None, lambda text: None)
        try:
            self.assertIn("Copy", dialog.copyButton.GetLabel())
            self.assertFalse(dialog.copyButton.IsEnabled())
            self.assertTrue(dialog.description.GetWindowStyleFlag() & self.wx.TE_READONLY)
            dialog.show_result("A red cup.", "Test model", 1.2)
            self.assertTrue(dialog.copyButton.IsEnabled())
            self.assertEqual(dialog.description.GetValue(), "A red cup.")
            self.assertIn("Close", dialog.closeButton.GetLabel())
        finally:
            dialog.Destroy()

    def test_settings_values_round_trip(self):
        expected = Options(detail="detailed", max_side=768, threads=3, speak=False)
        dialog = SettingsDialog(None, expected, lambda value: None, lambda: None, lambda: True)
        try:
            self.assertEqual(dialog.read_options(), expected)
        finally:
            dialog.Destroy()

    def test_invalid_settings_rejected(self):
        for values in [{"threads": 0}, {"detail": "unknown"}, {"max_side": 99999}]:
            with self.assertRaises(ValueError):
                Options(**values)

    def test_settings_mnemonics_precede_correct_control(self):
        dialog = SettingsDialog(None, Options(), lambda value: None, lambda: None, lambda: True)
        try:
            children = dialog.GetChildren()
            for label, control in [("Description &detail", dialog.detail),
                                   ("Maximum &image size", dialog.size), ("CPU &threads", dialog.threads)]:
                static = next(child for child in children if isinstance(child, self.wx.StaticText) and child.GetLabel() == label)
                self.assertEqual(children.index(control), children.index(static) + 1)
        finally:
            dialog.Destroy()
