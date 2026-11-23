import unittest
import tests
from drishya.geometry import Rect, fitted_size


class GeometryTests(unittest.TestCase):
    def test_negative_monitor_coordinates(self):
        self.assertEqual(Rect(-1500, 50, 400, 200).clip(Rect(-1920, 0, 3840, 1080)),
                         Rect(-1500, 50, 400, 200))

    def test_partial_target_clipped(self):
        self.assertEqual(Rect(-100, 0, 200, 50).clip(Rect(0, 0, 1920, 1080)),
                         Rect(0, 0, 100, 50))

    def test_offscreen_does_not_fall_back_to_screen(self):
        with self.assertRaises(ValueError):
            Rect(2000, 0, 100, 100).clip(Rect(0, 0, 1920, 1080))

    def test_empty_rectangle_rejected(self):
        for values in [(0, 0, 0, 5), (0, 0, 5, -1)]:
            with self.assertRaises(ValueError):
                Rect(*values)

    def test_preserves_aspect_ratio_without_upscaling(self):
        self.assertEqual(fitted_size(1920, 1080, 1024), (1024, 576))
        self.assertEqual(fitted_size(100, 200, 1024), (100, 200))
        self.assertEqual(fitted_size(1, 10000, 512), (1, 512))

    def test_invalid_size_rejected(self):
        with self.assertRaises(ValueError):
            fitted_size(0, 200, 512)
