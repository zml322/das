"""Regression checks for corrected stitched-file time inference."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QSettings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.classes.data_group import DataGroup
from utils.classes.data_timeline import (
    DataTimeline,
    parse_filename_end_time,
    recorded_end_time,
)
from utils.preferences import AppPreferences


class TimelineChecks(unittest.TestCase):
    def setUp(self):
        self.group = DataGroup.from_files(
            [
                r"D:\data\ch1_2026-08-26-16-54-19_2.bin",
                r"D:\data\ch1_2026-08-26-16-54-50_2.bin",
            ],
            [30720, 30720],
            520,
            1000,
        )
        self.headers = [
            [2026, 8, 26, 16, 54, 19],
            [2026, 8, 26, 16, 54, 50],
        ]

    def test_filename_time_is_the_recorded_file_end(self):
        parsed = parse_filename_end_time(self.group.segments[0].path)
        self.assertEqual(parsed, datetime(2026, 8, 26, 16, 54, 19))
        fallback, source = recorded_end_time("plain.bin", self.headers[0])
        self.assertEqual(fallback, parsed)
        self.assertEqual(source, "header")

    def test_device_behind_correction_is_added(self):
        timeline = DataTimeline.from_data_group(self.group, self.headers, 12.0)
        self.assertEqual(timeline.start_time, datetime(2026, 8, 26, 16, 54, 0, 280000))
        self.assertEqual(timeline.segments[0].corrected_recorded_end,
                         datetime(2026, 8, 26, 16, 54, 31))
        self.assertEqual(timeline.end_time, datetime(2026, 8, 26, 16, 55, 1, 720000))
        self.assertAlmostEqual(timeline.segments[1].end_time_difference_seconds, 0.28, places=6)
        self.assertEqual(timeline.discontinuities, ())

    def test_sample_and_wall_time_mapping_round_trip(self):
        timeline = DataTimeline.from_data_group(self.group, self.headers, 12.0)
        seam_time = timeline.absolute_time_for_sample(30720)
        self.assertEqual(seam_time, datetime(2026, 8, 26, 16, 54, 31))
        self.assertEqual(timeline.sample_boundary_for_time(seam_time), 30720)

    def test_large_recorded_time_difference_is_reported(self):
        headers = [self.headers[0], [2026, 8, 26, 16, 55, 10]]
        group = DataGroup.from_files(["first.bin", "second.bin"], [30720, 30720], 520, 1000)
        timeline = DataTimeline.from_data_group(group, headers, 12.0)
        self.assertEqual(len(timeline.discontinuities), 1)

    def test_preferences_are_persistent_and_typed(self):
        with tempfile.TemporaryDirectory(prefix="dasviewer-settings-") as directory:
            path = str(Path(directory) / "settings.ini")
            first = AppPreferences(QSettings(path, QSettings.IniFormat))
            first.set_time_correction_seconds(12.5)
            first.set_auto_reapply_filter(False)
            first.set_sidebar_width(512)
            second = AppPreferences(QSettings(path, QSettings.IniFormat))
            self.assertEqual(second.time_correction_seconds(), 12.5)
            self.assertFalse(second.auto_reapply_filter())
            self.assertEqual(second.sidebar_width(), 512)
            history = [{"name": "方案一", "steps": [{"algorithm": "bandpass"}]}]
            first.set_filter_pipeline_history(history)
            self.assertEqual(second.filter_pipeline_history(), history)
            second.settings.setValue(second.FILTER_HISTORY_KEY, "{invalid-json")
            self.assertEqual(second.filter_pipeline_history(), [])


if __name__ == "__main__":
    unittest.main()
