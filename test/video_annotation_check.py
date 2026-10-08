"""Regression checks for video/DAS mapping and persistent annotation projects."""

from __future__ import annotations

import csv
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys

import numpy as np
import pyqtgraph as pg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

from utils.classes.data_group import DataGroup
from utils.classes.data_timeline import DataTimeline, format_wall_time
from utils.classes.filter_pipeline import FilterStep
from utils.classes.vehicle_tracking import VehicleTrajectory
from utils.classes.video_trajectory import VideoTrajectoryWindow
from utils.classes.video_annotation import (
    AnnotationProject,
    format_video_position,
    parse_video_start_time,
    trajectory_candidates,
)
from utils.mainwindow import MainWindow


class VideoAnnotationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.group = DataGroup.from_files(
            [r"D:\data\ch1_2026-09-05-23-41-42_2.bin"],
            [10_000],
            16,
            1000,
        )
        self.timeline = DataTimeline.from_data_group(
            self.group,
            [[2026, 9, 5, 23, 41, 42]],
            correction_seconds=0.0,
        )
        self.assertEqual(self.timeline.start_time, datetime(2026, 9, 5, 23, 41, 32))

    def test_filename_time_and_clock_mapping(self):
        start = parse_video_start_time(r"D:\video\20260905_234112_tp00039.mp4")
        self.assertEqual(start, datetime(2026, 9, 5, 23, 41, 12))
        self.assertEqual(format_video_position(3_661_234), "01:01:01.234")

        project = AnnotationProject()
        project.set_video("camera.mp4", self.timeline.start_time)
        self.assertEqual(project.sync.sample_for_video_position(1_250, self.timeline), 1250)
        self.assertEqual(project.sync.video_position_for_sample(1250, self.timeline), 1250)

    def test_video_annotations_reproject_after_manual_alignment(self):
        project = AnnotationProject(camera_channel=8)
        project.set_video("camera.mp4", self.timeline.start_time)
        annotation = project.add_video_annotation(
            self.timeline,
            "车辆经过",
            "未核对",
            1000,
            note="测试",
        )
        self.assertEqual(annotation.start_sample, 1000)
        self.assertEqual(annotation.camera_channel, 8)
        self.assertEqual(annotation.source_domain, "video")

        project.sync.update(self.timeline.start_time, 0.5, 1.0)
        self.assertEqual(project.reproject_video_annotations(self.timeline), 1)
        self.assertEqual(annotation.start_sample, 1500)
        self.assertEqual(annotation.sync_revision, project.sync.revision)

        interval = project.add_video_annotation(
            self.timeline,
            "进入视野",
            "未核对",
            2000,
            end_video_ms=3000,
        )
        self.assertTrue(interval.is_interval)
        self.assertEqual((interval.start_sample, interval.end_sample), (2500, 3500))

    def test_context_guard_and_trajectory_candidates(self):
        project = AnnotationProject(camera_channel=8)
        project.set_video("camera.mp4", self.timeline.start_time)
        project.add_video_annotation(self.timeline, "车辆经过", "未核对", 1000)
        self.assertTrue(project.set_das_context(self.group, self.timeline))
        original_context = dict(project.das_context)

        other_group = DataGroup.from_files(["other.bin"], [10000], 16, 1000)
        other_timeline = DataTimeline.from_data_group(
            other_group,
            [[2026, 9, 5, 23, 41, 42]],
            correction_seconds=0.0,
        )
        self.assertFalse(project.set_das_context(other_group, other_timeline))
        self.assertEqual(project.das_context, original_context)

        trajectory = VehicleTrajectory(
            identifier=7,
            channels=np.array([6, 10], dtype=int),
            times=np.array([0.5, 1.5], dtype=float),
            coverage=1.0,
            projected_speed=20.0,
            quality=0.9,
        )
        candidates = trajectory_candidates([trajectory], 8, 1.0, tolerance_seconds=0.1)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].identifier, 7)
        self.assertAlmostEqual(candidates[0].crossing_seconds, 1.0)
        self.assertAlmostEqual(candidates[0].residual_ms, 0.0)

    def test_project_round_trip_and_csv_export(self):
        project = AnnotationProject(camera_name="东侧摄像头", camera_channel=4)
        project.set_video("camera.mp4", self.timeline.start_time)
        annotation = project.add_video_annotation(
            self.timeline,
            "车辆经过",
            "确认匹配",
            1250,
            note="清晰可见",
        )
        annotation.trajectory_identifier = 3
        annotation.time_residual_ms = -12.5
        self.assertTrue(project.set_das_context(self.group, self.timeline))

        with tempfile.TemporaryDirectory(prefix="das-video-annotation-") as directory:
            project_path = Path(directory) / "case.dasannotations.json"
            csv_path = Path(directory) / "case.csv"
            project.save(str(project_path))
            restored = AnnotationProject.load(str(project_path))
            self.assertEqual(restored.camera_name, "东侧摄像头")
            self.assertEqual(len(restored.annotations), 1)
            self.assertEqual(restored.annotations[0].start_sample, 1250)
            restored.export_csv(str(csv_path), self.timeline)
            with csv_path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["trajectory_id"], "3")
            self.assertEqual(rows[0]["das_start_sample"], "1250")

    def test_workspace_draws_camera_line_and_creates_video_label(self):
        window = MainWindow()
        raw = np.arange(800, dtype=np.float32).reshape(4, 200)
        window.raw_data = raw.copy()
        window.origin_data = raw.copy()
        window.sampling_rate = 1000.0
        window.channels_num = 4
        window.sampling_times = 200
        window.data_group = DataGroup.from_files(
            ["camera_case_2026-09-05-23-41-42.bin"], [200], 4, 1000
        )
        window._source_time_headers = [[2026, 9, 5, 23, 41, 42]]
        window.rebuildDataTimeline()
        window.initLocalParams()
        window.updateDataRange()
        window.updateDataParams()
        window.updateDataGPSTime()
        self.assertTrue(window.updateVideoAnnotationDataContext())
        window.video_annotation_project.set_video(
            "20260905_234132_camera.mp4", window.data_timeline.start_time
        )
        window._syncVideoProjectWidgets()
        window.plotVideoComparisonImage()
        self.assertFalse(hasattr(window, "video_camera_channel_end_spin_box"))
        self.assertEqual(window.video_camera_channel_apply_button.text(), "设置通道")
        self.assertEqual(window.video_sync_form.rowCount(), 1)
        self.assertEqual(window.video_trajectory_dx_spin_box.value(), 4.0)
        self.assertEqual(window._videoChannelBounds(), (1, 4))
        self.assertEqual(window.video_das_plot_widget.getViewBox().viewRange()[1], [0.0, 4.0])
        generation = window.video_trajectory_generation
        window.video_camera_channel_spin_box.setValue(3)
        window.applyVideoCameraChannel()
        self.assertEqual(window.video_annotation_project.camera_channel, 3)
        self.assertEqual(window.video_trajectory_generation, generation)
        self.assertAlmostEqual(window.video_camera_line.value(), 2.5)
        self.assertEqual(window.video_das_plot_widget.getViewBox().viewRange()[1], [0.0, 4.0])
        self.assertEqual(window.tab_widget.count(), 4)
        self.assertEqual(window.sidebar_tabs.count(), 3)
        window.tab_widget.setCurrentWidget(window.video_compare_container)
        self.assertIs(window.sidebar_tabs.currentWidget(), window.annotation_sidebar_widget)
        self.assertTrue(window.annotation_sidebar_widget.isAncestorOf(window.video_viewport))
        self.assertFalse(window.video_compare_container.isAncestorOf(window.video_viewport))
        self.assertIsNotNone(window.video_camera_line)
        self.assertTrue(window.video_playhead_line.movable)
        self.assertIn("DAS 时间：", window.video_playhead_line.toolTip())
        original_start = window.video_annotation_project.sync.video_start_time
        playhead = window.video_playhead_line
        playhead.setValue(0.1)
        window._videoPlayheadDragged(playhead)
        self.assertIn(
            format_wall_time(window.data_timeline.absolute_time_for_sample(100)),
            playhead.toolTip(),
        )
        window._videoPlayheadMoveFinished(playhead)
        self.assertEqual(
            window.video_annotation_project.sync.video_start_time,
            original_start + timedelta(seconds=0.1),
        )
        self.assertAlmostEqual(window.video_annotation_project.sync.manual_offset_seconds, 0.0)
        self.assertAlmostEqual(window.video_annotation_project.sync.rate, 1.0)
        self.assertTrue(window.video_sync_undo_button.isEnabled())
        window.undoVideoSyncCalibration()
        self.assertEqual(window.video_annotation_project.sync.video_start_time, original_start)
        window._alignCurrentVideoToDasSample(100)
        window.addVideoPointAnnotation()
        self.assertEqual(len(window.video_annotation_project.annotations), 1)
        self.assertEqual(window.video_annotation_project.annotations[0].start_sample, 100)
        self.assertIsNotNone(window.video_playhead_line)
        window.deleteLater()

    def test_video_das_prefetch_buffers_scroll_continuously_in_240_second_view(self):
        group = DataGroup.from_files(
            ["long_camera_case.bin"], [600_000], 16, 1000
        )
        timeline = DataTimeline.from_data_group(
            group,
            [[2026, 9, 5, 13, 54, 0]],
            correction_seconds=0.0,
        )
        first = VideoTrajectoryWindow(
            0,
            240_000,
            1,
            16,
            (),
            np.zeros((16, 20), dtype=np.float32),
            1000.0,
        )
        second = VideoTrajectoryWindow(
            120_000,
            360_000,
            1,
            16,
            (),
            np.ones((16, 20), dtype=np.float32),
            1000.0,
        )

        window = MainWindow()
        window.video_sequence_data_group = group
        window.video_sequence_timeline = timeline
        window.video_annotation_project.set_video("camera.mp4", timeline.start_time)
        window.video_annotation_context_matches = True
        window.video_trajectory_window_seconds = 240.0
        window.video_trajectory_parameters = None
        window.video_trajectory_windows = {
            (0, 240_000, 1, 16): first,
            (120_000, 360_000, 1, 16): second,
        }
        window.plotVideoComparisonImage()

        self.assertEqual(window.video_window_combo.currentData(), 240)
        image_items = [
            item
            for item in window.video_das_plot_widget.getPlotItem().items
            if isinstance(item, pg.ImageItem)
        ]
        self.assertEqual(len(image_items), 2)
        window._updateVideoPlayhead(120_000, force=True)
        x_range = window.video_das_plot_widget.getViewBox().viewRange()[0]
        self.assertAlmostEqual(x_range[0], 60.0)
        self.assertAlmostEqual(x_range[1], 300.0)
        window.deleteLater()

    def test_single_start_file_builds_metadata_only_video_sequence(self):
        with tempfile.TemporaryDirectory(prefix="das-video-sequence-") as directory:
            root = Path(directory)
            for second in (10, 11, 12):
                header = np.zeros(20, dtype="<f4")
                header[:6] = [2026, 9, 5, 5, 50, second]
                header[7:10] = [20, 4, 10]
                data = np.full((4, 20), second, dtype="<f4")
                target = root / f"ch1_2026-09-05-05-50-{second:02d}_2_20_4_10.bin"
                np.concatenate((header, data.ravel())).astype("<f4").tofile(target)

            window = MainWindow()
            window.file_path = str(root)
            window.updateFile()
            window.loadVideoSequenceFromStartRow(0)

            self.assertEqual(len(window.video_sequence_data_group.segments), 3)
            self.assertFalse(hasattr(window, "video_sequence_display_data"))
            self.assertIs(window._annotationTimeline(), window.video_sequence_timeline)
            self.assertIn("匹配 DAS：3 文件", window.video_sequence_status_label.text())
            self.assertIn("按窗口读取", window.video_sequence_status_label.text())
            self.assertIs(window.tab_widget.currentWidget(), window.video_compare_container)
            self.assertEqual(
                [step.algorithm for step in window._video_filter_steps],
                ["bandpass", "common_mode", "mad_normalize"],
            )
            self.assertEqual(
                [step.selection for step in window._video_filter_steps],
                [(1, 4, 1, 60)] * 3,
            )
            self.assertEqual(window._video_filter_steps[0].parameters, {
                "frequency_low": 0.01,
                "frequency_high": 1.0,
                "order": 4,
                "zero_phase": True,
            })
            self.assertEqual(
                window._video_filter_steps[1].parameters,
                {"method": "median"},
            )
            self.assertEqual(
                [step.processing_mode for step in window._video_filter_steps],
                ["continuous"] * 3,
            )
            self.assertEqual(
                window._videoTrajectoryParameters()["display_mode"],
                "current",
            )
            self.assertEqual(window.video_filter_summary_label.text(), "车辆事件增强")
            window.showVideoFilterDialog()
            self.assertIsNotNone(window.video_filter_dialog)
            self.assertEqual(window.video_filter_dialog.windowTitle(), "视频对照 · 二维显示滤波")
            window.setVideoFilterPipeline([
                FilterStep(
                    "mad_normalize", {}, (1, 4, 1, 60), "各通道 MAD 归一化"
                )
            ])
            self.assertEqual(window.video_filter_summary_label.text(), "1 步滤波")
            window.video_filter_dialog.close()
            window.deleteLater()

    def test_video_time_matching_reads_headers_and_excludes_unrelated_files(self):
        with tempfile.TemporaryDirectory(prefix="das-video-match-") as directory:
            root = Path(directory)
            for second in (5, 10, 20):
                header = np.zeros(20, dtype="<f4")
                header[:6] = [2026, 9, 5, 5, 50, second]
                header[7:10] = [20, 4, 10]
                data = np.zeros((4, 20), dtype="<f4")
                target = root / f"ch1_2026-09-05-05-50-{second:02d}_2_20_4_10.bin"
                np.concatenate((header, data.ravel())).astype("<f4").tofile(target)

            window = MainWindow()
            window.time_correction_seconds = 0.0
            window.video_annotation_project.sync.update(
                datetime(2026, 9, 5, 5, 50, 8), 0.0, 1.0
            )
            window.video_position_slider.setRange(0, 4_000)
            matches = window._matchingVideoDasPaths(str(root), margin_seconds=0.0)

            self.assertEqual(len(matches), 1)
            self.assertIn("05-50-10", os.path.basename(matches[0]))
            window.deleteLater()


if __name__ == "__main__":
    unittest.main()
