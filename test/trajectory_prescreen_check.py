"""Meaningful synthetic tracking and candidate-to-project workflow checks."""

import copy
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')
os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '1')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtWidgets import QApplication
from utils.classes.data_group import DataGroup
from utils.classes.data_timeline import DataTimeline
from utils.classes.trajectory_prescreen import (
    DEFAULT_PARAMETERS, TrackProposal, PrescreenResult, PrescreenCancelled,
    analyze_prescreen, detect_tracks, simplify_track,
)
from utils.classes.video_annotation import AnnotationProject
from utils.mainwindow import MainWindow
from utils.preferences import AppPreferences
from utils.theme import apply_application_theme


def traces(channels=64, duration=90, fs=20, *, crossing=False, partial=False, gaps=False):
    rng = np.random.default_rng(7)
    axis = np.arange(int(duration * fs)) / fs
    data = rng.normal(0, 0.04, (channels, len(axis)))
    truth = []
    for direction in ((1, -1) if crossing else (1,)):
        rows = np.arange(13, 50) if partial else np.arange(channels)
        times = 25 + 0.18 * rows + 0.0006 * rows ** 2 if direction > 0 else 40 - 0.22 * rows
        truth.append((rows, times))
        for row, center in zip(rows, times):
            if gaps and row in (27, 28, 29):
                continue
            data[row] += (6 if direction > 0 else -6) * np.exp(-0.5 * ((axis - center) / 0.09) ** 2)
    return data.astype(np.float32), truth


class AlgorithmChecks(unittest.TestCase):
    def assert_path(self, result, rows, times, fs=20, minimum=0.8):
        rows = rows + 1  # detector stores canonical 1-based channels
        matches = []
        for proposal in result.proposals:
            vertices = np.asarray(proposal.vertices)
            visible = (rows >= vertices[:, 1].min()) & (rows <= vertices[:, 1].max())
            if np.mean(visible) < minimum:
                continue
            predicted = np.interp(rows[visible], vertices[:, 1], vertices[:, 0] / fs)
            matches.append(float(np.median(np.abs(predicted - times[visible]))))
        self.assertTrue(matches, 'No proposal covers the ground-truth track')
        self.assertLess(min(matches), 0.15)

    def test_curved_internal_track_missing_rows_and_read_only_coordinates(self):
        data, truth = traces(partial=True, gaps=True)
        before = data.copy()
        result = detect_tracks(data, 20, DEFAULT_PARAMETERS)
        self.assert_path(result, *truth[0])
        np.testing.assert_array_equal(data, before)
        self.assertLessEqual(len(result.proposals), 2)
        self.assertGreaterEqual(result.proposals[0].vertices[0][1], 14)
        self.assertLess(len(result.proposals[0].vertices), 15)

    def test_opposing_crossing_paths_remain_separate(self):
        data, truth = traces(crossing=True)
        result = detect_tracks(data, 20, DEFAULT_PARAMETERS)
        for rows, times in truth:
            self.assert_path(result, rows, times)
        self.assertLessEqual(len(result.proposals), 4)

    def test_parallel_nearby_tracks_are_not_merged(self):
        data, truth = traces()
        axis = np.arange(data.shape[1]) / 20
        rows, times = truth[0]
        for row, center in zip(rows, times + 1.2):
            data[row] += 5 * np.exp(-0.5 * ((axis - center) / 0.09) ** 2)
        result = detect_tracks(data, 20, DEFAULT_PARAMETERS)
        self.assert_path(result, rows, times)
        self.assert_path(result, rows, times + 1.2)
        self.assertGreaterEqual(len(result.proposals), 2)

    def test_noise_and_static_channel_response_do_not_become_tracks(self):
        rng = np.random.default_rng(3)
        data = rng.normal(0, 0.08, (64, 1200))
        data[:, 400] += 7
        result = detect_tracks(data, 20, DEFAULT_PARAMETERS)
        self.assertEqual(len(result.proposals), 0)

    def test_duplicate_check_preserves_extensions_and_brief_crossings(self):
        from utils.classes.trajectory_prescreen import _duplicate_track
        from utils.classes.vehicle_tracking import VehicleTrajectory
        existing = VehicleTrajectory(1, np.arange(10, 30), np.arange(10, 30) * .2, 1, 20, 5)
        self.assertTrue(_duplicate_track(np.arange(12, 26), np.arange(12, 26) * .2, [existing], .12))
        self.assertFalse(_duplicate_track(np.arange(20, 45), np.arange(20, 45) * .2, [existing], .12))
        self.assertFalse(_duplicate_track(np.arange(10, 30), 8 - np.arange(10, 30) * .2, [existing], .12))

    def test_cancel_during_preprocessing(self):
        data, _ = traces(channels=32, duration=60)
        group = DataGroup.from_files(['source.bin'], [data.shape[1]], 32, 20)
        cancel = Event()
        def progress(percent, message):
            cancel.set()
        with self.assertRaises(PrescreenCancelled):
            analyze_prescreen(group, data, 500, 850, 1, 32, DEFAULT_PARAMETERS,
                              cancel=cancel, progress=progress)

    def test_cancel_and_simplify_endpoint_guarantee(self):
        cancel = Event()
        cancel.set()
        with self.assertRaises(PrescreenCancelled):
            detect_tracks(np.zeros((16, 100)), 20, DEFAULT_PARAMETERS, cancel=cancel)
        points = [[i * 20, i + 1] for i in range(40)]
        self.assertEqual(simplify_track(points, 20), [points[0], points[-1]])

    def test_preprocess_and_cross_file_mapping_matches_array_input(self):
        data, _truth = traces(channels=32, duration=60)
        count = data.shape[1]
        with tempfile.TemporaryDirectory(prefix='das-prescreen-bin-') as directory:
            paths = []
            for index, block in enumerate(np.array_split(data, 2, axis=1)):
                path = Path(directory) / f'part-{index}.bin'
                header = np.zeros(20, dtype='<f4')
                header[:6] = [2026, 9, 5, 13, 44, 33 + index]
                header[7:10] = [block.shape[1], block.shape[0], 20]
                np.concatenate((header, block.ravel())).astype('<f4').tofile(path)
                paths.append(str(path))
            group = DataGroup.from_files(paths, [count // 2] * 2, 32, 20)
            before = data.copy()
            from_array = analyze_prescreen(group, data, 500, 850, 5, 30, DEFAULT_PARAMETERS)
            from_files = analyze_prescreen(group, None, 500, 850, 5, 30, DEFAULT_PARAMETERS)
            self.assertTrue(from_files.proposals)
            self.assertEqual([p.vertices for p in from_files.proposals], [p.vertices for p in from_array.proposals])
            for proposal in from_files.proposals:
                self.assertTrue(all(500 <= p[0] < 850 and 5 <= p[1] <= 30 for p in proposal.vertices))
            np.testing.assert_array_equal(data, before)
            self.assertIn('短记录', from_files.notes[0])

    def test_invalid_scope_and_frequency_are_explicit_errors(self):
        group = DataGroup.from_files(['none.bin'], [200], 16, 20)
        with self.assertRaisesRegex(ValueError, '8'):
            analyze_prescreen(group, np.zeros((16, 200)), 0, 200, 1, 4, DEFAULT_PARAMETERS)
        with self.assertRaisesRegex(ValueError, '滤波'):
            analyze_prescreen(group, np.zeros((16, 200)), 0, 200, 1, 16, {'frequency_high': 20})


class ReviewChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        cls.app = QApplication.instance() or QApplication([])
        apply_application_theme(cls.app)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='das-prescreen-review-')
        settings = QSettings(str(Path(self.temporary.name) / 'settings.ini'), QSettings.IniFormat)
        self.window = MainWindow(preferences=AppPreferences(settings))
        w = self.window
        w.setAttribute(Qt.WA_DontShowOnScreen, True)
        w.data_group = DataGroup.from_files(['source.bin'], [1200], 32, 20)
        w.data_timeline = DataTimeline.from_data_group(w.data_group, [[2026, 9, 5, 13, 45, 33]], correction_seconds=0)
        w.raw_data, self.truth = traces(channels=32, duration=60)
        w.origin_data = w.raw_data.copy()
        w.updateVideoAnnotationDataContext()
        w.plotVideoComparisonImage()
        w.tab_widget.setCurrentWidget(w.video_compare_container)
        self.controller = w.trajectory_prescreen
        from utils.classes.trajectory_prescreen_ui import ReviewDialog
        self.controller.dialog = ReviewDialog(self.controller)
        self.controller.dialog.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.controller.show()
        self.controller.context = self.controller.current_context()
        self.controller.detected_dx = 4
        self.controller.candidates = {
            1: TrackProposal(1, [[400, 4], [450, 12], [550, 20]], 0.9, 4),
            2: TrackProposal(2, [[600, 8], [650, 18]], 1, 4),
        }
        self.controller.refresh()
        w.plotVideoComparisonImage(preserve_view=True)

    def tearDown(self):
        self.controller.shutdown()
        if self.controller.future is not None:
            try:
                self.controller.future.result(timeout=10)
            except PrescreenCancelled:
                pass
        w = self.window
        w.video_trajectory_executor.shutdown(wait=True, cancel_futures=True)
        w.video_media_executor.shutdown(wait=True, cancel_futures=True)
        w.hide()
        self.controller.dialog.hide()
        w.deleteLater()
        self.app.processEvents()
        self.temporary.cleanup()

    def test_edit_batch_accept_undo_redo_and_project_roundtrip(self):
        w, c = self.window, self.controller
        self.assertEqual(w.video_annotation_project.annotations, [])
        c.edit(1)
        self.assertEqual(w.annotation_canvas._edit_id, -1)
        w.annotation_canvas._edit_items[1].setPos(21, 5.5)
        w.annotation_canvas.commit_edit()
        self.assertTrue(c.candidates[1].edited)
        self.assertFalse(w.video_annotation_dirty)
        vertices = copy.deepcopy(c.candidates[1].vertices)
        w.annotation_quick_vehicle_combo.setCurrentText('小车')
        w.annotation_quick_lane_combo.setCurrentIndex(2)
        w.annotation_quick_direction_combo.setEditText('东→西')
        c.accept([1, 2, 1])
        annotations = w.video_annotation_project.annotations
        self.assertEqual(len(annotations), 2)
        self.assertEqual(annotations[0].vertices, vertices)
        self.assertEqual((annotations[0].vehicle_type, annotations[0].lane), ('小车', 3))
        self.assertTrue(all(a.source_domain == 'das' and a.geometry_type == 'lin' for a in annotations))
        self.assertEqual(c.candidates, {})
        w.undoLastVideoAnnotation()
        self.assertEqual(w.video_annotation_project.annotations, [])
        w.redoVideoAnnotation()
        self.assertEqual(len(w.video_annotation_project.annotations), 2)
        path = str(Path(self.temporary.name) / 'project.dasannotations.json')
        w.video_annotation_project.save(path)
        loaded = AnnotationProject.load(path)
        self.assertEqual(loaded.annotations[0].vertices, vertices)
        import csv
        import json
        csv_path = Path(self.temporary.name) / 'annotations.csv'
        loaded.export_csv(str(csv_path), w._annotationTimeline())
        with csv_path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 2)
        self.assertEqual(json.loads(rows[0]['vertices_sample_channel']), vertices)
        self.assertEqual((rows[0]['vehicle_type'], rows[0]['lane']), ('小车', '3'))

    def test_delete_and_rescan_do_not_touch_confirmed_annotations(self):
        w, c = self.window, self.controller
        c.accept([1])
        before = copy.deepcopy(w.video_annotation_project.to_dict())
        w._deleteAnnotationFromPlot(-2)
        self.assertEqual(c.candidates, {})
        c.invalidate()
        self.assertEqual(w.video_annotation_project.to_dict(), before)
        self.assertNotIn(-2, w.annotation_canvas._ann_geoms)

    def test_background_detection_freezes_scope_and_keeps_raw_data(self):
        w, c = self.window, self.controller
        w.video_das_plot_widget.getViewBox().setRange(xRange=(25, 42), yRange=(4, 30), padding=0)
        before = w.raw_data.copy()
        c.start()
        self.assertIsNotNone(c.future)
        result = c.future.result(timeout=20)
        c.poll()
        self.assertTrue(result.proposals)
        self.assertTrue(c.candidates)
        self.assertFalse(w.video_follow_checkbox.isChecked())
        np.testing.assert_array_equal(w.raw_data, before)
        self.assertEqual(w.video_annotation_project.annotations, [])

    def test_stale_result_is_discarded_after_project_switch(self):
        from concurrent.futures import Future
        c, w = self.controller, self.window
        future = Future()
        future.prescreen_context = c.current_context()
        future.prescreen_generation = c.generation
        future.prescreen_dx = 4
        future.set_result(PrescreenResult(tuple(c.candidates.values())))
        c.future = future
        c.started_at = time.perf_counter()
        w.newVideoAnnotationProject()
        c.poll()
        self.assertFalse(c.candidates)
        self.assertEqual(w.video_annotation_project.annotations, [])

    def test_narrow_and_wide_preview(self):
        w = self.window
        preview = os.environ.get('DAS_PRESCREEN_PREVIEW_DIR')
        for width, height in ((1024, 700), (1440, 900)):
            w.resize(width, height)
            w.show()
            for _ in range(3):
                self.app.processEvents()
            self.assertEqual(w.width(), width)
            self.assertGreater(w.video_das_plot_widget.height(), height * 0.45)
            if preview:
                w.grab().save(str(Path(preview) / f'prescreen-{width}.png'))
                self.controller.dialog.grab().save(str(Path(preview) / 'prescreen-review.png'))
                self.controller.dialog.advanced_scroll.show()
                self.app.processEvents()
                self.controller.dialog.grab().save(str(Path(preview) / 'prescreen-review-advanced.png'))
                self.controller.dialog.advanced_scroll.hide()


if __name__ == '__main__':
    unittest.main()
