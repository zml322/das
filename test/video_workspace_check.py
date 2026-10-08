"""Regressions for new-project source retention, view reset and narrow layouts."""

import copy
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')
os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '1')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtWidgets import QApplication, QMessageBox
from utils.classes.data_group import DataGroup
from utils.classes.data_timeline import DataTimeline
from utils.mainwindow import MainWindow
from utils.preferences import AppPreferences
from utils.theme import apply_application_theme


class VideoWorkspaceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        cls.app = QApplication.instance() or QApplication([])
        apply_application_theme(cls.app)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='das-workspace-check-')
        settings = QSettings(str(Path(self.temporary.name) / 'settings.ini'), QSettings.IniFormat)
        self.window = MainWindow(preferences=AppPreferences(settings))
        self.window.setAttribute(Qt.WA_DontShowOnScreen, True)
        w = self.window
        w.data_group = DataGroup.from_files(['case.bin'], [6000], 64, 10)
        w.data_timeline = DataTimeline.from_data_group(
            w.data_group, [[2026, 9, 5, 13, 54, 33]], correction_seconds=0
        )
        w.origin_data = np.random.default_rng(1).normal(size=(64, 6000)).astype(np.float32)
        w.updateVideoAnnotationDataContext()
        w.plotVideoComparisonImage()
        w.tab_widget.setCurrentWidget(w.video_compare_container)

    def tearDown(self):
        w = self.window
        w.video_trajectory_executor.shutdown(wait=True, cancel_futures=True)
        w.video_media_executor.shutdown(wait=True, cancel_futures=True)
        w.hide()
        w.deleteLater()
        self.app.processEvents()
        self.temporary.cleanup()

    def test_new_project_preserves_windowed_context_and_video(self):
        w = self.window
        w.video_sequence_data_group, w.video_sequence_timeline = w.data_group, w.data_timeline
        w.data_group = w.data_timeline = None
        w.video_das_match_required = True
        project = w.video_annotation_project
        project.set_video('camera.mp4', datetime(2026, 9, 5, 13, 44, 33))
        project.sync.update(project.sync.video_start_time, 1.25, 1.0001)
        project.set_camera_channel(20)
        project.direction_labels = ['东→西']
        project.add_geometry_annotation(w.video_sequence_timeline, 'bbox', [(10, 2), (15, 2), (15, 8), (10, 8)], '车辆经过', '未核对')
        project.project_path = 'old.dasannotations.json'
        w.video_position_slider.setRange(0, 600_000)
        w.video_position_slider.setValue(123_000)
        w.video_source_label.setText('camera.mp4')
        w.video_ffmpeg_position_ms = 123_000
        w.video_playback_backend = 'ffmpeg'
        sync = copy.deepcopy(project.sync.to_dict())
        with patch.object(w, '_requestVideoTrajectoryForPosition'), patch.object(w.video_player, 'setMedia') as reset_media:
            w.newVideoAnnotationProject()
        reset_media.assert_not_called()
        self.assertEqual(w.video_annotation_project.video_path, 'camera.mp4')
        self.assertEqual(w.video_annotation_project.sync.to_dict(), sync)
        self.assertEqual(w.video_annotation_project.camera_channel, 20)
        self.assertEqual(w.video_position_slider.maximum(), 600_000)
        self.assertEqual(w.video_source_label.text(), 'camera.mp4')
        self.assertEqual(w._currentVideoPosition(), 123_000)
        self.assertEqual(w.video_annotation_project.annotations, [])
        self.assertEqual(w.video_annotation_project.project_path, '')
        self.assertIs(w._annotationTimeline(), w.video_sequence_timeline)
        self.assertTrue(w.video_camera_channel_apply_button.isEnabled())
        w.video_camera_channel_spin_box.setValue(25)
        w.applyVideoCameraChannel()
        self.assertEqual(w.video_annotation_project.camera_channel, 25)
        w._setAnnotationDrawingTool('bbox')
        self.assertTrue(w.annotation_canvas.busy)
        w.annotation_canvas.cancel()

    def test_new_project_rebinds_normal_data_without_video(self):
        w = self.window
        w.newVideoAnnotationProject()
        self.assertIs(w._annotationTimeline(), w.data_timeline)
        self.assertTrue(w.annotation_plot_tool_buttons['bbox'].isEnabled())

    def test_cancel_new_project_keeps_annotations(self):
        w = self.window
        project = w.video_annotation_project
        project.add_geometry_annotation(w.data_timeline, 'bbox', [(10, 2), (15, 2), (15, 8), (10, 8)], '车辆经过', '未核对')
        w.video_annotation_dirty = True
        with patch('utils.mainwindow.QMessageBox.question', return_value=QMessageBox.No):
            w.newVideoAnnotationProject()
        self.assertIs(w.video_annotation_project, project)
        self.assertEqual(len(project.annotations), 1)

    def test_reset_view_restores_time_and_channels_without_changing_geometry(self):
        w = self.window
        annotation = w.video_annotation_project.add_geometry_annotation(
            w.data_timeline, 'bbox', [(10, 2), (15, 2), (15, 8), (10, 8)], '车辆经过', '未核对'
        )
        before = copy.deepcopy(annotation.vertices)
        view = w.video_das_plot_widget.getViewBox()
        view.setRange(xRange=(100, 180), yRange=(10, 20), padding=0)
        w.resetVideoComparisonView()
        np.testing.assert_allclose(view.viewRange(), [[0, 600], [0, 64]])
        w.video_annotation_project.set_video('camera.mp4', w.data_timeline.start_time)
        w.video_playback_backend = 'ffmpeg'
        w.video_ffmpeg_position_ms = 300_000
        w.video_follow_checkbox.setChecked(False)
        w.annotation_canvas.set_mode('bbox')
        view.setRange(xRange=(100, 180), yRange=(10, 20), padding=0)
        w.video_reset_view_button.click()
        np.testing.assert_allclose(view.viewRange(), [[240, 480], [0, 64]])
        self.assertEqual(annotation.vertices, before)
        self.assertTrue(w.annotation_canvas.busy)

    def test_resizing_wraps_controls_and_keeps_time_visible(self):
        w = self.window
        preview_dir = os.environ.get('DAS_WORKSPACE_PREVIEW_DIR')
        for width, height in ((1440, 900), (1024, 700), (1366, 768)):
            w.resize(width, height)
            w.main_splitter.setSizes([380, width - 410])
            w.show()
            for _ in range(3):
                self.app.processEvents()
            self.assertEqual(w.width(), width)
            self.assertFalse(w.event_range_widget.isVisible())
            panel = w.video_sidebar_panel
            for child in (w.video_time_label, w.video_position_slider, w.video_fit_combo,
                          w.video_forward_button):
                rect = child.rect()
                rect.moveTopLeft(child.mapTo(panel, rect.topLeft()))
                self.assertTrue(panel.rect().contains(rect), (width, child.objectName(), rect))
            time = w.video_time_label
            self.assertGreaterEqual(time.width(), time.fontMetrics().horizontalAdvance(time.text()))
            scroll = w.annotation_controls_scroll
            for child in (w.video_start_time_edit, w.annotation_direction_combo):
                rect = child.rect()
                rect.moveTopLeft(child.mapTo(scroll.widget(), rect.topLeft()))
                self.assertLessEqual(rect.right(), scroll.widget().width())
            for child in list(w.annotation_plot_tool_buttons.values()) + [
                w.annotation_quick_direction_combo, w.video_focus_button, w.video_reset_view_button
            ]:
                panel = w.video_compare_container
                rect = child.rect()
                rect.moveTopLeft(child.mapTo(panel, rect.topLeft()))
                self.assertTrue(panel.rect().contains(rect), (width, child.text() if hasattr(child, 'text') else 'direction', rect))
            self.assertGreater(w.video_das_plot_widget.height(), height * 0.5)
            if preview_dir:
                w.grab().save(str(Path(preview_dir) / f'workspace-{width}x{height}.png'))
        w.video_focus_button.setChecked(True)
        w.video_focus_button.setChecked(False)
        self.assertFalse(w.event_range_widget.isVisible())
        w.tab_widget.setCurrentWidget(w.gray_scale_container)
        self.assertTrue(w.event_range_widget.isVisible())


if __name__ == '__main__':
    unittest.main()
