"""Small smoke check for the transplanted geometry workflow and sidecar I/O."""
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from PyQt5.QtWidgets import QApplication
from utils.classes.data_group import DataGroup
from utils.classes.data_timeline import DataTimeline
from utils.classes.video_annotation import AnnotationProject
from utils.mainwindow import MainWindow


class GeometrySmokeCheck(unittest.TestCase):
    def test_create_edit_undo_save_reload_and_clock_correction(self):
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window.data = np.zeros((16, 10_000), dtype=np.float32)
        window.origin_data = window.data.copy()
        window.raw_data = window.data.copy()
        window.channels_num = 16
        window.sampling_times = 10_000
        window.sampling_rate = 1000
        window.data_group = DataGroup.from_files(['case_2026-09-05-23-41-42.bin'], [10_000], 16, 1000)
        window._source_time_headers = [[2026, 9, 5, 23, 41, 42]]
        window.time_correction_seconds = 0
        window.rebuildDataTimeline()
        window.initLocalParams()
        window.updateDataRange()
        window.updateDataParams()
        window.updateDataGPSTime()
        window.updateVideoAnnotationDataContext()
        window.video_annotation_project.set_video('camera.mp4', datetime(2026, 9, 5, 23, 41, 32))
        window.video_position_slider.setRange(0, 10_000)
        window.plotVideoComparisonImage()
        window.annotation_quick_vehicle_combo.setCurrentText('小车')
        window.annotation_quick_lane_combo.setCurrentIndex(2)
        window.annotation_quick_direction_combo.setEditText('东→西')

        canvas = window.annotation_canvas
        canvas.set_mode('bbox')
        canvas._handle_click_bbox(1, 2)
        canvas._handle_click_bbox(3, 5)
        self.assertFalse(canvas.busy)
        box = window.video_annotation_project.annotations[-1]
        self.assertEqual(box.geometry_type, 'bbox')
        self.assertEqual(box.start_sample, 1000)
        self.assertEqual((box.vehicle_type, box.lane, box.travel_direction), ('小车', 3, '东→西'))
        canvas.start_edit(box.identifier)
        canvas._edit_items[1].setPos(1.5, 2.5)
        canvas.commit_edit()
        self.assertEqual(box.start_sample, 1500)
        window.undoLastVideoAnnotation()
        self.assertEqual(window.video_annotation_project.annotations[0].start_sample, 1000)
        window.redoVideoAnnotation()
        self.assertEqual(window.video_annotation_project.annotations[0].start_sample, 1500)

        canvas.set_mode('obb')
        canvas._handle_click_obb(4, 4)
        canvas._handle_click_obb(6, 8)
        canvas._handle_click_obb(5, 6.5)
        self.assertEqual(window.video_annotation_project.annotations[-1].geometry_type, 'obb')
        tilted = window.video_annotation_project.annotations[-1]
        canvas.start_edit(tilted.identifier)
        canvas._edit_items[3].setPos(5, 6.6)
        canvas.commit_edit()
        self.assertEqual(len(tilted.vertices), 4)

        class Click:
            def double(self):
                return False

        canvas.set_mode('kp')
        canvas._handle_click_multipoint(2, 3, Click())
        canvas._finalise_multipoint()
        canvas.set_mode('lin')
        canvas._handle_click_multipoint(2, 4.5, Click())
        canvas._handle_click_multipoint(4, 8.5, Click())
        canvas._finalise_multipoint()
        track = window.video_annotation_project.annotations[-1]
        self.assertAlmostEqual(track.track_measurement(1000)[0], 28.8)

        window._addVideoAnnotation(2000)
        before = [a.to_dict()['vertices'] for a in window.video_annotation_project.annotations[:4]]
        with patch.object(window.preferences, 'set_time_correction_seconds'):
            window.setTimeCorrectionSeconds(0.25)
        self.assertEqual(before, [a.vertices for a in window.video_annotation_project.annotations[:4]])
        self.assertEqual(window.video_annotation_project.annotations[-1].start_sample, 1750)
        self.assertEqual(window.video_annotation_project.das_correction_seconds, 0.25)
        self.assertIn('东→西', window.video_annotation_project.direction_labels)
        with tempfile.TemporaryDirectory(prefix='das-geometry-') as temporary:
            path = Path(temporary) / 'project.dasannotations.json'
            window.video_annotation_project.save(str(path))
            restored = AnnotationProject.load(str(path))
            self.assertEqual(restored.to_dict(), window.video_annotation_project.to_dict())
            restored.export_csv(str(Path(temporary) / 'labels.csv'), window.data_timeline)

        legacy = window.video_annotation_project.to_dict()
        legacy['schema_version'] = 1
        legacy['annotations'] = [legacy['annotations'][-1]]
        self.assertEqual(AnnotationProject.from_dict(legacy).annotations[0].shape_label, '时点')
        preview = os.environ.get('DAS_ANNOTATION_PREVIEW')
        if preview:
            from utils.theme import apply_application_theme
            apply_application_theme(app)
            window.resize(1440, 900)
            window.tab_widget.setCurrentWidget(window.video_compare_container)
            window.show()
            app.processEvents()
            window.grab().save(preview)
        window.video_trajectory_executor.shutdown(wait=True, cancel_futures=True)
        window.video_media_executor.shutdown(wait=True, cancel_futures=True)
        window.deleteLater()
        app.processEvents()


if __name__ == '__main__':
    unittest.main()
