"""Focused regression checks for read-only video/DAS long-window support."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.bin_reader import bin_window
from utils.classes.data_group import DataGroup
from utils.classes.video_annotation import AnnotationProject, trajectory_candidates
from utils.classes.video_media import (
    PLAYBACK_CACHE_FRAME_RATE,
    build_playback_cache_command,
    cached_mpeg_ps_copy,
    probe_video,
)
from utils.classes.vehicle_tracking import VehicleTrajectory
from utils.classes.video_trajectory import analyze_group_window, read_group_window, required_window_seconds


def _pts(value: int) -> bytes:
    value = int(value)
    return bytes((
        0x21 | ((value >> 29) & 0x0E),
        (value >> 22) & 0xFF,
        0x01 | ((value >> 14) & 0xFE),
        (value >> 7) & 0xFF,
        0x01 | ((value << 1) & 0xFE),
    ))


def _pes(pts: int, payload: bytes) -> bytes:
    return b"\x00\x00\x01\xE0\x00\x00\x80\x80\x05" + _pts(pts) + payload


def _write_bin(path: Path, data: np.ndarray, second: int) -> None:
    channels, samples = data.shape
    header = np.zeros(20, dtype="<f4")
    header[:6] = [2026, 9, 5, 13, 44, second]
    header[7:10] = [samples, channels, 10]
    np.concatenate((header, data.astype("<f4").ravel())).tofile(path)


class VideoPipelineChecks(unittest.TestCase):
    def test_playback_cache_command_preserves_timeline_and_uses_fixed_rate(self):
        command = build_playback_cache_command(
            Path("camera.mp4"),
            Path("camera-cache.mp4"),
            ("libx264", ["-c:v", "libx264"]),
        )
        self.assertLess(command.index("-dts_delta_threshold"), command.index("-i"))
        threshold_index = command.index("-dts_delta_threshold")
        self.assertEqual(command[threshold_index + 1], "3600")
        filter_index = command.index("-vf")
        self.assertEqual(command[filter_index + 1], f"fps={PLAYBACK_CACHE_FRAME_RATE:g}")

    def test_mpeg_ps_probe_uses_pts_and_cache_never_targets_source(self):
        with tempfile.TemporaryDirectory(prefix="das-video-media-") as directory:
            root = Path(directory)
            source = root / "camera.mp4"
            source.write_bytes(
                b"\x00\x00\x01\xBA" + b"\x44" * 12
                + _pes(90_000, b"\x00\x00\x00\x01\x67\x42")
                + _pes(270_000, b"\x00\x00\x01\x65\x88")
                + b"\x00\x00\x01\xB9" + b"\x00" * 31
            )
            before = source.read_bytes()
            result = probe_video(source)
            self.assertTrue(result.is_mpeg_program_stream)
            self.assertEqual(result.video_codec, "H.264/AVC")
            self.assertAlmostEqual(result.duration_seconds, 2.0)
            self.assertEqual(result.completion_state, "terminated")
            self.assertEqual(result.trailing_zero_bytes, 31)
            cached = cached_mpeg_ps_copy(source, root / "cache")
            self.assertEqual(cached.suffix, ".mpg")
            self.assertNotEqual(cached.resolve(), source.resolve())
            self.assertEqual(cached.read_bytes(), before)
            self.assertEqual(source.read_bytes(), before)

    def test_window_read_crosses_two_bin_files_without_full_group_read(self):
        with tempfile.TemporaryDirectory(prefix="das-video-window-") as directory:
            root = Path(directory)
            first = np.arange(24, dtype=np.float32).reshape(3, 8)
            second = (100 + np.arange(24, dtype=np.float32)).reshape(3, 8)
            first_path = root / "ch1_2026-09-05-13-44-08_2_8_3_10.bin"
            second_path = root / "ch1_2026-09-05-13-44-16_2_8_3_10.bin"
            _write_bin(first_path, first, 8)
            _write_bin(second_path, second, 16)
            self.assertTrue(np.array_equal(bin_window(first_path, 2, 6, 1, 3), first[1:3, 2:6]))
            group = DataGroup.from_files([str(first_path), str(second_path)], [8, 8], 3, 10)
            actual = read_group_window(group, 5, 12, 2, 3)
            expected = np.concatenate((first[1:3, 5:8], second[1:3, :4]), axis=1)
            self.assertTrue(np.array_equal(actual, expected))

    def test_low_frequency_window_rule_and_range_candidate_metadata(self):
        self.assertEqual(required_window_seconds({"frequency_low": 0.01}, 120), 200.0)
        track = VehicleTrajectory(
            7, np.array([4, 8, 12]), np.array([0.0, 1.0, 2.0]),
            coverage=0.8, projected_speed=20.0, quality=0.75,
        )
        candidates = trajectory_candidates([track], (7, 9), 1.0, 0.01)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].direction, "向通道增大")
        self.assertAlmostEqual(candidates[0].confidence, 0.6)

    def test_long_window_runs_existing_preprocess_and_picker_across_files(self):
        with tempfile.TemporaryDirectory(prefix="das-video-analyze-") as directory:
            root = Path(directory)
            # 200 seconds at 10 Hz satisfies the 0.01 Hz two-period guard.
            samples = 1_000
            time = np.arange(samples, dtype=float) / 10.0
            first = np.vstack([np.sin(2 * np.pi * 0.2 * time + channel) for channel in range(8)]).astype(np.float32)
            second = np.vstack([np.sin(2 * np.pi * 0.2 * time + channel + 0.1) for channel in range(8)]).astype(np.float32)
            first[0] = 0.0  # A dead trace must be repaired before band-pass.
            first_path = root / "ch1_2026-09-05-13-44-00_2_1000_8_10.bin"
            second_path = root / "ch1_2026-09-05-13-45-40_2_1000_8_10.bin"
            _write_bin(first_path, first, 0)
            _write_bin(second_path, second, 40)
            group = DataGroup.from_files([str(first_path), str(second_path)], [samples, samples], 8, 10)
            window = analyze_group_window(group, 0, 2_000, 1, 8, {
                "channel_spacing": 2.0,
                "frequency_low": 0.01,
                "frequency_high": 1.0,
                "target_sampling_rate": 5.0,
                "seed_width": 4,
                "peak_prominence": 1.5,
                "minimum_separation": 0.8,
                "prominence_window": 12.0,
                "minimum_speed": 2.0,
                "maximum_speed": 60.0,
                "tracking_tolerance": 0.15,
                "minimum_coverage": 0.55,
                "maximum_missed_channels": 3,
                "direction": "auto",
                "polarity": "auto",
            })
            self.assertEqual((window.start_sample, window.end_sample), (0, 2_000))
            self.assertEqual(window.processed_data.shape[0], 8)
            self.assertAlmostEqual(window.processed_sampling_rate, 5.0)

    def test_range_and_two_point_calibration_evidence_round_trip(self):
        project = AnnotationProject(camera_channel=4)
        project.set_camera_channel_range(4, 12)
        project.calibration_anchors = [
            {"video_position_ms": 1_000, "das_sample": 1_500},
            {"video_position_ms": 101_000, "das_sample": 101_520},
        ]
        restored = AnnotationProject.from_dict(project.to_dict())
        self.assertEqual(restored.camera_channel_range, (4, 12))
        self.assertEqual(restored.calibration_anchors, project.calibration_anchors)


if __name__ == "__main__":
    unittest.main()
