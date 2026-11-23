import sys
import types
import unittest
from unittest.mock import patch
import wx
import tests
from drishya.geometry import Rect
from drishya.wgc import capture_with_wgc


class WgcTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)

    def test_bgra_pixels_are_converted_to_rgb(self):
        backend = types.SimpleNamespace(isSupported=lambda: True,
            captureImage=lambda info: bytes([0, 0, 255, 255, 255, 0, 0, 255]))
        module = types.SimpleNamespace(RecogImageInfo=lambda *args: args, _wgcCapture=backend)
        with patch.dict(sys.modules, {"contentRecog": module}):
            image = capture_with_wgc(Rect(-10, 5, 2, 1))
        self.assertEqual(bytes(image.GetData()), bytes([255, 0, 0, 0, 0, 255]))

    def test_unsupported_capture_does_not_call_backend(self):
        backend = types.SimpleNamespace(isSupported=lambda: False,
            captureImage=lambda info: self.fail("Unsupported capture was attempted"))
        module = types.SimpleNamespace(RecogImageInfo=lambda *args: args, _wgcCapture=backend)
        with patch.dict(sys.modules, {"contentRecog": module}):
            self.assertIsNone(capture_with_wgc(Rect(0, 0, 2, 1)))
