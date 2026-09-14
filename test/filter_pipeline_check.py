"""Regression checks for the v2.1.9 filter history and stitched data model."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtCore import QEventLoop, QTimer
from PyQt5.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.classes.data_group import DataGroup, natural_sort_key
from utils.classes.das_filter import DASFilterDialog
from utils.classes.das_filter import apply_das_filter
from utils.classes.filter_pipeline import (
    FilterPipeline,
    FilterStep,
    replay_filter_pipeline,
)
from utils.mainwindow import MainWindow
from utils.bin_reader import bin2numpy


def simple_filter(data, _sampling_rate, algorithm, parameters):
    if algorithm == "add":
        return data + float(parameters["value"])
    if algorithm == "scale":
        return data * float(parameters["value"])
    if algorithm == "demean":
        return data - np.mean(data, axis=1, keepdims=True)
    raise ValueError(algorithm)


def wait_for_dialog(dialog: DASFilterDialog, timeout_ms: int = 10000) -> None:
    worker = dialog._worker
    if worker is None or not worker.isRunning():
        QApplication.processEvents()
        return
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec_()
    QApplication.processEvents()
    if dialog.is_busy():
        raise TimeoutError("filter pipeline worker did not finish")


class FilterPipelineChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_replay_order_and_selected_range_invariance(self):
        raw = np.arange(36, dtype=np.float32).reshape(3, 12)
        steps = [
            FilterStep("add", {"value": 2}, (2, 3, 3, 10), "add"),
            FilterStep("scale", {"value": 3}, (2, 2, 5, 8), "scale"),
        ]
        result = replay_filter_pipeline(raw, 1000, steps, simple_filter)
        expected = raw.copy()
        expected[1:3, 2:10] += 2
        expected[1:2, 4:8] *= 3
        np.testing.assert_array_equal(result, expected)
        np.testing.assert_array_equal(result[0], raw[0])

    def test_disabled_and_per_segment_steps(self):
        raw = np.array([[0, 2, 4, 10, 12, 14]], dtype=np.float32)
        disabled = FilterStep("add", {"value": 99}, (1, 1, 1, 6), "disabled", enabled=False)
        demean = FilterStep(
            "demean",
            {},
            (1, 1, 1, 6),
            "demean",
            processing_mode="per_segment",
        )
        result = replay_filter_pipeline(raw, 1, [disabled, demean], simple_filter, [(0, 3), (3, 6)])
        np.testing.assert_array_equal(result, np.array([[-2, 0, 2, -2, 0, 2]], dtype=np.float32))

    def test_pipeline_edit_operations_clone_state(self):
        first = FilterStep("add", {"value": 1}, (1, 1, 1, 2), "first")
        second = FilterStep("scale", {"value": 2}, (1, 1, 1, 2), "second")
        pipeline = FilterPipeline([first, second])
        self.assertEqual(pipeline.move(1, -1), 0)
        pipeline.set_enabled(0, False)
        snapshot = pipeline.steps()
        snapshot[0].parameters["value"] = 100
        self.assertEqual(pipeline.steps()[0].parameters["value"], 2)
        pipeline.remove(1)
        self.assertEqual(len(pipeline), 1)

    def test_non_modal_dialog_replays_and_lists_steps(self):
        raw = np.arange(48, dtype=np.float32).reshape(4, 12)
        dialog = DASFilterDialog(
            raw,
            1000,
            visible_range=(1, 4, 1, 12),
            segment_ranges=[(0, 6), (6, 12)],
        )
        self.assertFalse(dialog.isModal())
        step = FilterStep("mad_normalize", {}, (2, 3, 2, 10), "各通道 MAD 归一化")
        dialog._start_replay([step], "test", 0)
        wait_for_dialog(dialog)
        self.assertEqual(len(dialog.pipeline_steps()), 1)
        self.assertEqual(dialog.history_list.count(), 1)
        np.testing.assert_array_equal(dialog.working_data[0], raw[0])
        dialog._delete_selected_step()
        wait_for_dialog(dialog)
        self.assertEqual(len(dialog.pipeline_steps()), 0)
        np.testing.assert_array_equal(dialog.working_data, raw)
        dialog.frequency_low.setValue(17.0)
        dialog.set_data(
            np.zeros((3, 20), dtype=np.float32),
            1000,
            (1, 3, 1, 20),
            previous_steps=[step],
            segment_ranges=[(0, 10), (10, 20)],
        )
        self.assertEqual(dialog.frequency_low.value(), 17.0)
        self.assertEqual(dialog.pipeline_steps(), [])
        self.assertTrue(dialog.reuse_steps_button.isEnabled())
        dialog.deleteLater()

    def test_main_window_keeps_one_filter_tool_and_receives_pipeline(self):
        window = MainWindow()
        raw = np.arange(800, dtype=np.float32).reshape(4, 200)
        window.raw_data = raw.copy()
        window.raw_data.setflags(write=False)
        window.origin_data = raw.copy()
        window.sampling_rate = 1000.0
        window.channels_num = 4
        window.sampling_times = 200
        window.data_group = DataGroup.from_files(
            ["first.bin", "second.bin"],
            [100, 100],
            4,
            1000,
        )
        window.initLocalParams()
        window.updateDataRange()
        window.updateDataParams()
        window.showDASFilterDialog()
        dialog = window.das_filter_dialog
        self.assertIsNotNone(dialog)
        self.assertFalse(dialog.isModal())
        window.showDASFilterDialog()
        self.assertIs(window.das_filter_dialog, dialog)

        step = FilterStep("mad_normalize", {}, (2, 3, 2, 100), "各通道 MAD 归一化")
        dialog._start_replay([step], "main-window-test", 0)
        wait_for_dialog(dialog)
        self.assertEqual(len(window._das_filter_steps), 1)
        np.testing.assert_array_equal(window.origin_data[0], raw[0])
        self.assertFalse(np.array_equal(window.origin_data[1, 1:100], raw[1, 1:100]))
        dialog.hide()
        window.deleteLater()

    def test_stitched_file_identifiers_and_selection(self):
        window = MainWindow()
        raw = np.arange(800, dtype=np.float32).reshape(4, 200)
        window.raw_data = raw.copy()
        window.raw_data.setflags(write=False)
        window.origin_data = raw.copy()
        window.sampling_rate = 1000.0
        window.channels_num = 4
        window.sampling_times = 200
        window.data_group = DataGroup.from_files(
            [
                r"D:\data\ch1_2026-08-26-16-54-19_2.bin",
                r"D:\data\ch1_2026-08-26-16-54-50_2.bin",
            ],
            [100, 100],
            4,
            1000,
        )
        window.initLocalParams()
        window.updateDataRange()
        window.updateDataParams()
        window.updateStitchedFilesList()
        window.plotGrayScaleImage()
        window.plotMultiWavesImage()

        self.assertEqual(window.stitched_files_list.count(), 2)
        self.assertIn("16-54-19", window.stitched_files_list.item(0).text())
        visuals = window.plot_gray_scale_widget._file_segment_visuals
        self.assertEqual([visual["index"] for visual in visuals], [0, 1])
        multi_visuals = window.plot_multi_waves_widget._file_segment_visuals
        self.assertEqual([visual["index"] for visual in multi_visuals], [0, 1])
        self.assertEqual(window.fileSegmentLabel(0, 100), "1  16:54:19")
        self.assertEqual(window.fileSegmentLabel(1, 20), "2")

        details = window.fileSegmentDetails(1)
        self.assertIn(r"D:\data\ch1_2026-08-26-16-54-50_2.bin", details)
        self.assertIn("全局采样范围：101 - 200", details)
        self.assertIn("起止相对时间：0.1 - 0.2 s", details)
        self.assertEqual(visuals[1]["bar"].toolTip(), details)

        window.stitched_files_list.setCurrentRow(1)
        QApplication.processEvents()
        self.assertEqual(window.selected_file_segment_index, 1)
        self.assertIn("第 2/2 段", window.statusBar().currentMessage())
        self.assertEqual(visuals[0]["bar"].brush().color().alpha(), 60)
        self.assertEqual(visuals[1]["bar"].brush().color().alpha(), 112)
        self.assertEqual(multi_visuals[1]["bar"].brush().color().alpha(), 112)
        window.deleteLater()

    def test_real_bin_stitch_metadata_and_parameter_persistence(self):
        files = sorted((PROJECT_ROOT / "test").glob("*.bin"), key=lambda p: natural_sort_key(p.name))
        self.assertGreaterEqual(len(files), 2)
        window = MainWindow()
        window.file_names = [str(path) for path in files[:2]]
        window.file_path = str(files[0].parent)
        window.readData()
        self.assertEqual(window.raw_data.shape, (520, 61440))
        self.assertEqual(window.data_group.boundaries, [30720])
        self.assertEqual([segment.sample_count for segment in window.data_group.segments], [30720, 30720])

        previous = FilterStep("mad_normalize", {}, (1, 2, 1, 100), "MAD")
        window._das_filter_settings = {"algorithm": "mad_normalize"}
        window._das_filter_steps = [previous]
        window.file_names = [str(files[1])]
        window.readData()
        self.assertEqual(window._das_filter_settings["algorithm"], "mad_normalize")
        self.assertEqual(window._das_filter_steps, [])
        self.assertEqual(len(window._last_das_filter_steps), 1)
        self.assertEqual(window.data_group.total_samples, 30720)
        window.deleteLater()

    def test_real_bin_local_pipeline_preserves_unselected_data(self):
        source = sorted((PROJECT_ROOT / "test").glob("*.bin"), key=lambda p: natural_sort_key(p.name))[0]
        raw = bin2numpy(source, 0, 2)[:, :1000].copy()
        step = FilterStep(
            "bandpass",
            {
                "frequency_low": 5.0,
                "frequency_high": 120.0,
                "order": 4,
                "zero_phase": True,
            },
            (1, 1, 101, 900),
            "带通滤波",
        )
        result = replay_filter_pipeline(raw, 1000, [step], apply_das_filter)
        self.assertEqual(result.shape, raw.shape)
        self.assertTrue(np.all(np.isfinite(result)))
        np.testing.assert_array_equal(result[1], raw[1])
        np.testing.assert_array_equal(result[0, :100], raw[0, :100])
        np.testing.assert_array_equal(result[0, 900:], raw[0, 900:])


if __name__ == "__main__":
    unittest.main()
