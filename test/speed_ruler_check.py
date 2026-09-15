"""Regression checks for the interactive DAS projected-speed ruler."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.classes.speed_ruler import SpeedRulerROI, calculate_projected_speed
from utils.mainwindow import MainWindow


class SpeedRulerChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_projected_speed_and_direction_are_endpoint_order_invariant(self):
        increasing = calculate_projected_speed((1.0, 10.0), (3.0, 20.0), 4.0)
        self.assertTrue(increasing.valid)
        self.assertAlmostEqual(increasing.distance_m, 40.0)
        self.assertAlmostEqual(increasing.speed_mps, 20.0)
        self.assertAlmostEqual(increasing.speed_kmh, 72.0)
        self.assertEqual(increasing.direction_text, "通道递增")

        swapped = calculate_projected_speed((3.0, 20.0), (1.0, 10.0), 4.0)
        self.assertAlmostEqual(swapped.speed_mps, 20.0)
        self.assertEqual(swapped.direction_text, "通道递增")

        decreasing = calculate_projected_speed((1.0, 20.0), (3.0, 10.0), 4.0)
        self.assertEqual(decreasing.direction_text, "通道递减")
        self.assertAlmostEqual(decreasing.speed_mps, 20.0)

        vertical = calculate_projected_speed((1.0, 10.0), (1.0, 20.0), 4.0)
        self.assertFalse(vertical.valid)

    def test_roi_handle_movement_and_dx_change_update_label(self):
        ruler = SpeedRulerROI([(0.0, 1.0), (2.0, 11.0)], 4.0)
        self.assertEqual(ruler.pen.color().name(), "#ffea00")
        self.assertGreater(ruler.halo_pen.widthF(), ruler.pen.widthF())
        self.assertTrue(all(handle.radius == 8 for handle in ruler.getHandles()))
        self.assertIn("20.00 m/s", ruler.labelText())
        self.assertIn("72.00 km/h", ruler.labelText())

        ruler.movePoint(ruler.getHandles()[1], (1.0, 11.0), finish=False)
        QApplication.processEvents()
        self.assertIn("40.00 m/s", ruler.labelText())
        ruler.setChannelSpacing(2.0)
        self.assertIn("20.00 m/s", ruler.labelText())

    def test_main_window_ruler_survives_redraw_without_modifying_data(self):
        window = MainWindow()
        raw = np.arange(20_000, dtype=np.float32).reshape(20, 1000)
        window.raw_data = raw.copy()
        window.raw_data.setflags(write=False)
        window.origin_data = raw.copy()
        window.sampling_rate = 100.0
        window.channels_num = 20
        window.sampling_times = 1000
        window.initLocalParams()
        window.updateDataRange()
        window.updateDataParams()
        window.plotGrayScaleImage()
        baseline = window.origin_data.copy()

        window.addOrResetSpeedRuler()
        first_ruler = window.speed_ruler_roi
        self.assertTrue(window.speed_ruler_active)
        self.assertIsNotNone(first_ruler)
        self.assertEqual(window.speed_ruler_channel_spacing, 4.0)
        self.assertAlmostEqual(first_ruler.measurement().speed_mps, 20.0)
        self.assertIn("m/s", window.speed_ruler_status_label.text())

        first_ruler.movePoint(first_ruler.getHandles()[0], (1.0, 2.5), finish=False)
        QApplication.processEvents()
        stored_points = window.speed_ruler_points
        expected = calculate_projected_speed(stored_points[0], stored_points[1], 4.0)
        self.assertIn(f"{expected.speed_mps:.2f} m/s", window.speed_ruler_status_label.text())

        first_ruler.translate((0.5, 1.0))
        QApplication.processEvents()
        translated_points = window.speed_ruler_points
        for translated, original in zip(translated_points, stored_points):
            np.testing.assert_allclose(translated, (original[0] + 0.5, original[1] + 1.0))
        translated_speed = calculate_projected_speed(translated_points[0], translated_points[1], 4.0)
        self.assertAlmostEqual(translated_speed.speed_mps, expected.speed_mps)
        stored_points = translated_points

        window.plotGrayScaleImage()
        self.assertIsNot(window.speed_ruler_roi, first_ruler)
        for actual, expected_point in zip(window.speed_ruler_points, stored_points):
            np.testing.assert_allclose(actual, expected_point)
        np.testing.assert_array_equal(window.origin_data, baseline)

        previous_speed = window.speed_ruler_roi.measurement().speed_mps
        window.speed_ruler_spacing_spin_box.setValue(2.0)
        QApplication.processEvents()
        self.assertAlmostEqual(window.speed_ruler_roi.measurement().speed_mps, previous_speed / 2.0)
        window.removeSpeedRuler()
        self.assertFalse(window.speed_ruler_active)
        self.assertIsNone(window.speed_ruler_roi)
        np.testing.assert_array_equal(window.origin_data, baseline)
        window.deleteLater()


if __name__ == "__main__":
    unittest.main()
