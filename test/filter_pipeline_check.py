"""Regression checks for the v2.1.14 filter sidebar, history, and stitched data."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt5.QtCore import QEventLoop, QSettings, QTimer, Qt
from PyQt5.QtWidgets import QApplication, QDoubleSpinBox, QMessageBox

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.classes.data_group import DataGroup, natural_sort_key
from utils.classes.das_filter import DASFilterDialog
from utils.classes.das_filter import apply_das_filter
from utils.classes.filter_history import (
    MAX_RECENT_PIPELINES,
    add_recent_history,
    history_entry_steps,
    make_history_entry,
    normalize_history,
    upsert_named_history,
)
from utils.classes.filter_pipeline import (
    FilterPipeline,
    FilterStep,
    replay_filter_pipeline,
)
from utils.mainwindow import MainWindow
from utils.bin_reader import bin2numpy
from utils.preferences import AppPreferences


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

    def test_persistent_filter_history_validates_replaces_and_deduplicates(self):
        first = FilterStep("bandpass", {"frequency_low": 1.0, "frequency_high": 20.0}, (1, 4, 1, 100), "带通")
        second = FilterStep("highpass", {"frequency": 2.0}, (1, 4, 1, 100), "高通")
        named = make_history_entry("车辆方案", "named", [first], (4, 100), 1000)
        history = upsert_named_history([], named)
        replacement = make_history_entry("车辆方案", "named", [second], (4, 100), 1000)
        history = upsert_named_history(history, replacement)
        self.assertEqual(len(history), 1)
        self.assertEqual(history_entry_steps(history[0])[0].algorithm, "highpass")

        recent = make_history_entry("最近", "recent", [second], (4, 100), 1000)
        history = add_recent_history(history, recent)
        history = add_recent_history(
            history,
            make_history_entry("重复", "recent", [second], (4, 100), 1000),
        )
        self.assertEqual(len(history), 2)
        for index in range(MAX_RECENT_PIPELINES + 3):
            step = FilterStep("highpass", {"frequency": 3.0 + index}, (1, 4, 1, 100), "高通")
            history = add_recent_history(
                history,
                make_history_entry(str(index), "recent", [step], (4, 100), 1000),
            )
        self.assertEqual(sum(entry["kind"] == "recent" for entry in history), MAX_RECENT_PIPELINES)
        self.assertEqual(normalize_history([{}, history[0], history[0]]), [history[0]])

    def test_saved_filter_validation_rejects_unknown_algorithm(self):
        window = MainWindow()
        window.sampling_rate = 1000.0
        unknown = FilterStep("retired_filter", {}, (1, 1, 1, 10), "旧版算法")
        with self.assertRaisesRegex(ValueError, "未知滤波算法"):
            window.validateFilterStepsForCurrentData([unknown])
        window.deleteLater()

    def test_non_modal_dialog_replays_and_lists_steps(self):
        raw = np.arange(48, dtype=np.float32).reshape(4, 12)
        dialog = DASFilterDialog(
            raw,
            1000,
            visible_range=(1, 4, 1, 12),
            segment_ranges=[(0, 6), (6, 12)],
            auto_reapply=False,
        )
        self.assertFalse(dialog.isModal())
        self.assertEqual(dialog.minimumWidth(), 380)
        self.assertLessEqual(dialog.width(), 430)
        self.assertFalse(dialog.scroll_area.horizontalScrollBar().isVisible())
        self.assertTrue(dialog.channel_from.isHidden())
        dialog.scope_combo.setCurrentIndex(dialog.scope_combo.findData("custom"))
        self.assertFalse(dialog.channel_from.isHidden())
        self.assertFalse(dialog.auto_reapply_checkbox.isChecked())
        step = FilterStep("mad_normalize", {}, (2, 3, 2, 10), "各通道 MAD 归一化")
        preview_events = []
        committed_events = []
        dialog.previewReady.connect(lambda *_args: preview_events.append(True))
        dialog.committed.connect(lambda *_args: committed_events.append(True))
        self.assertTrue(dialog.set_draft_pipeline([step], "测试载入"))
        self.assertIsNone(dialog._worker)
        np.testing.assert_array_equal(dialog.working_data, raw)
        dialog.history_list.item(0).setCheckState(Qt.Unchecked)
        QApplication.processEvents()
        self.assertIsNone(dialog._worker)
        np.testing.assert_array_equal(dialog.working_data, raw)
        dialog.history_list.item(0).setCheckState(Qt.Checked)
        QApplication.processEvents()
        dialog._apply_pipeline()
        wait_for_dialog(dialog)
        self.assertEqual(len(dialog.pipeline_steps()), 1)
        self.assertEqual(dialog.history_list.count(), 1)
        np.testing.assert_array_equal(dialog.working_data[0], raw[0])
        self.assertEqual(preview_events, [])
        self.assertEqual(len(committed_events), 1)
        applied = dialog.working_data.copy()
        dialog._reset()
        wait_for_dialog(dialog)
        np.testing.assert_array_equal(dialog.working_data, raw)
        self.assertEqual(len(dialog.pipeline_steps()), 1)
        self.assertTrue(dialog.apply_button.isEnabled())
        dialog._apply_pipeline()
        wait_for_dialog(dialog)
        np.testing.assert_array_equal(dialog.working_data, applied)
        dialog._delete_selected_step()
        self.assertEqual(len(dialog.pipeline_steps()), 0)
        np.testing.assert_array_equal(dialog.working_data, applied)
        dialog._reset()
        wait_for_dialog(dialog)
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
        self.assertEqual(len(dialog.previous_steps), 1)
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
        window.sidebar_tabs.setCurrentWidget(window.filter_sidebar_widget)
        QApplication.processEvents()
        dialog = window.das_filter_dialog
        QApplication.processEvents()
        self.assertIsNotNone(dialog)
        self.assertFalse(dialog.isModal())
        self.assertTrue(dialog.embedded)
        self.assertFalse(dialog.isWindow())
        self.assertIs(window.sidebar_tabs.currentWidget(), window.filter_sidebar_widget)
        self.assertEqual(dialog.windowFlags() & Qt.WindowType_Mask, Qt.Widget)
        self.assertEqual(dialog.add_step_button.text(), "加入滤波链")
        self.assertEqual(dialog.apply_button.text(), "应用滤波")
        self.assertEqual(dialog.reset_button.text(), "恢复原始数据")
        self.assertFalse(hasattr(dialog, "accept_button"))
        self.assertFalse(hasattr(dialog, "cancel_button"))
        self.assertFalse(hasattr(dialog, "close_button"))
        self.assertFalse(hasattr(dialog, "reuse_steps_button"))
        self.assertEqual(dialog.history_list.horizontalScrollBar().maximum(), 0)
        self.assertEqual(window.overview_form.verticalSpacing(), 4)
        self.assertEqual(window.gps_from_line_edit.maximumHeight(), 28)
        self.assertEqual(window.gps_from_line_edit.objectName(), "metadataValue")
        self.assertEqual(window.sidebar_tabs.minimumWidth(), 320)
        self.assertEqual(window.data_sidebar_widget.layout().spacing(), 12)
        self.assertEqual(window.plot_toolbar.layout().count(), 3)
        self.assertTrue(window.event_markers_visible_checkbox.isChecked())
        self.assertIsInstance(window.time_correction_spin_box, QDoubleSpinBox)
        self.assertEqual(set(dialog.filter_sections), {"algorithm", "range", "parameters", "pipeline"})
        range_section = dialog.filter_sections["range"]
        self.assertTrue(range_section.header.isChecked())
        range_section.header.click()
        QApplication.processEvents()
        self.assertFalse(range_section.header.isChecked())
        self.assertTrue(range_section.content.isHidden())
        self.assertEqual(dialog._selected_range(), (1, 4, 1, 200))
        range_section.header.click()
        QApplication.processEvents()
        self.assertTrue(range_section.header.isChecked())
        self.assertFalse(range_section.content.isHidden())
        window.showDASFilterDialog()
        self.assertIs(window.das_filter_dialog, dialog)

        step = FilterStep("mad_normalize", {}, (2, 3, 2, 100), "各通道 MAD 归一化")
        dialog.set_draft_pipeline([step], "main-window-test")
        np.testing.assert_array_equal(window.origin_data, raw)
        dialog._apply_pipeline()
        wait_for_dialog(dialog)
        self.assertEqual(len(window._das_filter_steps), 1)
        np.testing.assert_array_equal(window.origin_data[0], raw[0])
        self.assertFalse(np.array_equal(window.origin_data[1, 1:100], raw[1, 1:100]))
        window.show()
        QApplication.processEvents()
        with patch("utils.mainwindow.QMessageBox.question", return_value=QMessageBox.Yes):
            self.assertTrue(window.close())
        QApplication.processEvents()
        self.assertFalse(window.isVisible())

    def test_saved_filter_history_survives_restart_and_loads_as_preview(self):
        with tempfile.TemporaryDirectory(prefix="dasviewer-filter-history-") as directory:
            settings_path = str(Path(directory) / "settings.ini")
            preferences = AppPreferences(QSettings(settings_path, QSettings.IniFormat))
            window = MainWindow(preferences=preferences)
            raw = np.arange(800, dtype=np.float32).reshape(4, 200)
            window.raw_data = raw.copy()
            window.raw_data.setflags(write=False)
            window.origin_data = raw.copy()
            window.sampling_rate = 1000.0
            window.channels_num = 4
            window.sampling_times = 200
            window.data_group = DataGroup.from_files(["history.bin"], [200], 4, 1000)
            window.initLocalParams()
            window.updateDataRange()
            window.updateDataParams()
            window.showDASFilterDialog()

            step = FilterStep("mad_normalize", {}, (1, 4, 1, 200), "各通道 MAD 归一化")
            window.das_filter_dialog.pipeline = FilterPipeline([step])
            window.das_filter_dialog._refresh_history()
            window.saveCurrentFilterPipeline("车辆通用方案")

            restarted = AppPreferences(QSettings(settings_path, QSettings.IniFormat))
            saved = normalize_history(restarted.filter_pipeline_history())
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["name"], "车辆通用方案")
            self.assertEqual(saved[0]["kind"], "named")

            window.das_filter_dialog.pipeline = FilterPipeline()
            window.das_filter_dialog._refresh_history()
            window.loadSavedFilterPipeline(saved[0]["identifier"])
            self.assertIsNone(window.das_filter_dialog._worker)
            self.assertEqual(len(window.das_filter_dialog.pipeline_steps()), 1)
            self.assertEqual(window._das_filter_steps, [])
            self.assertEqual(window.das_filter_dialog.committed_steps, [])

            window.das_filter_dialog._commit_current()
            wait_for_dialog(window.das_filter_dialog)
            self.assertEqual(len(window._das_filter_steps), 1)
            self.assertEqual(window._das_filter_steps[0].selection, (1, 4, 1, 200))
            stored = normalize_history(restarted.filter_pipeline_history())
            self.assertEqual([entry["kind"] for entry in stored], ["named", "recent"])
            window.das_filter_dialog._commit_current()
            stored = normalize_history(restarted.filter_pipeline_history())
            self.assertEqual(len(stored), 2)

            window.deleteSavedFilterPipeline(saved[0]["identifier"])
            stored = normalize_history(restarted.filter_pipeline_history())
            self.assertEqual([entry["kind"] for entry in stored], ["recent"])
            window.das_filter_dialog.hide()
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
        window._source_time_headers = [
            [2026, 8, 26, 16, 54, 19],
            [2026, 8, 26, 16, 54, 20],
        ]
        window.time_correction_seconds = 12.0
        window.rebuildDataTimeline()
        window.initLocalParams()
        window.updateDataRange()
        window.updateDataParams()
        window.updateDataGPSTime()
        window.updateStitchedFilesList()
        window.plotGrayScaleImage()
        window.plotSingleChannelTime()
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

        baseline = window.origin_data.copy()
        window.setEventSampleRange(25, 175)
        self.assertEqual(window.event_range_from_edit.text(), "2026-08-26 16:54:30.925")
        self.assertEqual(window.event_range_to_edit.text(), "2026-08-26 16:54:31.075")
        for plot_widget in (
            window.plot_gray_scale_widget,
            window.plot_single_channel_time_widget,
            window.plot_multi_waves_widget,
        ):
            visual = plot_widget._event_range_visual
            self.assertEqual(
                tuple(visual["region"].getRegion()),
                (0.025, 0.175),
            )
            self.assertEqual(visual["region"].brush.color().alpha(), 0)
            self.assertEqual(visual["region"].hoverBrush.color().alpha(), 0)
            self.assertEqual(visual["region"].lines[0].pen.width(), 3)
            self.assertEqual(visual["region"].lines[1].pen.width(), 3)
            self.assertEqual(visual["region"].zValue(), 30)
        visible_range_before_toggle = (window.sampling_times_from_num, window.sampling_times_to_num)
        window.event_markers_visible_checkbox.setChecked(False)
        QApplication.processEvents()
        self.assertEqual(
            (window.sampling_times_from_num, window.sampling_times_to_num),
            visible_range_before_toggle,
        )
        self.assertTrue(all(
            plot_widget._event_range_visual is None
            for plot_widget in (
                window.plot_gray_scale_widget,
                window.plot_single_channel_time_widget,
                window.plot_multi_waves_widget,
            )
        ))
        window.event_markers_visible_checkbox.setChecked(True)
        QApplication.processEvents()
        self.assertTrue(all(
            plot_widget._event_range_visual["region"].zValue() == 30
            for plot_widget in (
                window.plot_gray_scale_widget,
                window.plot_single_channel_time_widget,
                window.plot_multi_waves_widget,
            )
        ))
        window.viewEventRange()
        self.assertEqual((window.sampling_times_from_num, window.sampling_times_to_num), (26, 175))
        self.assertEqual(window.gps_from_line_edit.text(), "2026-08-26 16:54:30.925")
        self.assertEqual(window.gps_to_line_edit.text(), "2026-08-26 16:54:31.075")
        self.assertEqual(
            window.plot_gray_scale_widget.time_axis.tickStrings([0.025, 0.175], 1, 0.05),
            ["16:54:30.925", "16:54:31.075"],
        )
        np.testing.assert_array_equal(window.origin_data, baseline)
        window.restoreFullEventRange()
        self.assertEqual((window.sampling_times_from_num, window.sampling_times_to_num), (1, 200))
        self.assertEqual(window.gps_from_line_edit.text(), "2026-08-26 16:54:30.900")
        self.assertEqual(window.gps_to_line_edit.text(), "2026-08-26 16:54:31.100")
        window.deleteLater()

    def test_sidebar_time_correction_requires_explicit_apply_and_persists(self):
        with tempfile.TemporaryDirectory(prefix="dasviewer-time-correction-") as directory:
            settings_path = str(Path(directory) / "settings.ini")
            preferences = AppPreferences(QSettings(settings_path, QSettings.IniFormat))
            window = MainWindow(preferences=preferences)
            raw = np.arange(400, dtype=np.float32).reshape(4, 100)
            window.raw_data = raw.copy()
            window.raw_data.setflags(write=False)
            window.origin_data = raw.copy()
            window.sampling_rate = 1000.0
            window.channels_num = 4
            window.sampling_times = 100
            window.data_group = DataGroup.from_files(
                [r"D:\data\ch1_2026-08-26-16-54-19_2.bin"],
                [100],
                4,
                1000,
            )
            window._source_time_headers = [[2026, 8, 26, 16, 54, 19]]
            window.initLocalParams()
            window.rebuildDataTimeline()
            window.updateDataRange()
            window.updateDataParams()
            window.updateDataGPSTime()

            previous = window.time_correction_seconds
            window.time_correction_spin_box.setValue(7.5)
            self.assertEqual(window.time_correction_seconds, previous)
            window.time_correction_apply_button.click()

            self.assertEqual(window.time_correction_seconds, 7.5)
            self.assertEqual(preferences.time_correction_seconds(), 7.5)
            self.assertEqual(window.time_correction_spin_box.value(), 7.5)
            self.assertEqual(
                window.data_timeline.segments[0].corrected_recorded_end,
                datetime(2026, 8, 26, 16, 54, 26, 500000),
            )
            window.deleteLater()

    def test_file_table_selection_waits_for_explicit_confirmation(self):
        with tempfile.TemporaryDirectory(prefix="dasviewer-selection-") as directory:
            names = ["part1.bin", "part2.bin", "part10.bin"]
            for name in names:
                (Path(directory) / name).touch()

            window = MainWindow()
            window.file_path = directory
            window.updateFile()
            calls = []

            def fake_read_data():
                calls.append(("read", list(window.file_names)))
                paths = [window.dataFilePath(name) for name in window.file_names]
                window.data_group = DataGroup.from_files(paths, [1] * len(paths), 1, 1)

            window.readData = fake_read_data
            window.initLocalParams = lambda: calls.append(("init", None))
            window.updateAll = lambda: calls.append(("update", None))
            window.syncDASFilterDialog = lambda: calls.append(("sync", None))

            window.files_table_widget.item(0, 0).setSelected(True)
            window.files_table_widget.item(2, 0).setSelected(True)
            QApplication.processEvents()

            self.assertEqual(calls, [])
            self.assertEqual(window.selectedFileRows(), [0, 2])
            self.assertIn("待拼接：2 个文件", window.pending_file_selection_label.text())
            self.assertTrue(window.load_selected_files_button.isEnabled())

            window.load_selected_files_button.click()
            self.assertEqual(
                calls,
                [
                    ("read", ["part1.bin", "part10.bin"]),
                    ("init", None),
                    ("update", None),
                    ("sync", None),
                ],
            )
            self.assertEqual(window.pending_file_selection_label.text(), "当前已加载：2 个文件")
            self.assertFalse(window.load_selected_files_button.isEnabled())
            window.deleteLater()

    def test_auto_reapply_adapts_full_range_and_replays_from_new_baseline(self):
        window = MainWindow()
        new_raw = np.arange(1500, dtype=np.float32).reshape(5, 300)
        window.raw_data = new_raw.copy()
        window.raw_data.setflags(write=False)
        window.origin_data = new_raw.copy()
        window.sampling_rate = 1000.0
        window.channels_num = 5
        window.sampling_times = 300
        window.data_group = DataGroup.from_files(["next.bin"], [300], 5, 1000)
        window._last_das_filter_shape = (4, 200)
        window._last_das_filter_steps = [
            FilterStep("mad_normalize", {}, (1, 4, 1, 200), "MAD")
        ]
        window._das_filter_steps = []
        window.auto_reapply_filter_pipeline = True
        window.initLocalParams()
        window.updateDataRange()
        window.updateDataParams()

        adapted = window.adaptPreviousFilterSteps()
        self.assertEqual(adapted[0].selection, (1, 5, 1, 300))
        window.showDASFilterDialog()
        window.syncDASFilterDialog()
        wait_for_dialog(window.das_filter_dialog)
        self.assertEqual(window._das_filter_steps[0].selection, (1, 5, 1, 300))
        self.assertFalse(np.array_equal(window.origin_data, new_raw))

        window._last_das_filter_steps = [
            FilterStep("mad_normalize", {}, (1, 4, 50, 350), "局部 MAD")
        ]
        window._last_das_filter_shape = (4, 400)
        with self.assertRaisesRegex(ValueError, "超出当前数据"):
            window.adaptPreviousFilterSteps()
        window.das_filter_dialog.hide()
        window.deleteLater()

    def test_real_bin_stitch_metadata_and_parameter_persistence(self):
        files = sorted((PROJECT_ROOT / "test").glob("*.bin"), key=lambda p: natural_sort_key(p.name))
        self.assertGreaterEqual(len(files), 2)
        window = MainWindow()
        window.time_correction_seconds = 12.0
        window.file_path = str(files[0].parent)
        window.updateFile()
        selected_names = {path.name for path in files[:2]}
        for row in range(window.files_table_widget.rowCount()):
            item = window.files_table_widget.item(row, 0)
            item.setSelected(item.text() in selected_names)
        QApplication.processEvents()
        self.assertIsNone(window.raw_data)
        self.assertTrue(window.load_selected_files_button.isEnabled())
        window.load_selected_files_button.click()
        self.assertEqual(window.raw_data.shape, (520, 61440))
        self.assertEqual(window.data_group.boundaries, [30720])
        self.assertEqual([segment.sample_count for segment in window.data_group.segments], [30720, 30720])
        self.assertEqual(
            window.data_timeline.start_time.isoformat(timespec="milliseconds"),
            "2026-08-26T16:54:00.280",
        )
        self.assertEqual(
            window.data_timeline.end_time.isoformat(timespec="milliseconds"),
            "2026-08-26T16:55:01.720",
        )
        self.assertAlmostEqual(
            window.data_timeline.segments[1].end_time_difference_seconds,
            0.28,
            places=6,
        )
        window.plot_gray_scale_widget.setTimeOrigin(window.data_timeline.start_time)
        self.assertEqual(
            window.plot_gray_scale_widget.time_axis.tickStrings([0, 30.72], 1, 10),
            ["16:54:00.280", "16:54:31.000"],
        )
        highlighted = {
            window.files_table_widget.item(row, 0).text()
            for row in range(window.files_table_widget.rowCount())
            if window.files_table_widget.item(row, 0).isSelected()
        }
        self.assertEqual(highlighted, {path.name for path in files[:2]})

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
