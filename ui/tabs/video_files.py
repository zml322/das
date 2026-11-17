"""Video-time matching and metadata-only BIN sequence loading."""

import os.path
from datetime import datetime, timedelta

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QFileDialog, QProgressDialog

from core.data.bin_loader import validate_bin_paths
from core.data.bin_reader import read_bin_header
from core.data.data_group import DataGroup, natural_sort_key
from core.data.data_timeline import (
    DataTimeline,
    format_wall_time,
    parse_filename_end_time,
    recorded_end_time,
)
from core.video.annotation import parse_video_start_time
from ui.components.window_feature import WindowFeature
from ui.tabs.video_constants import VIDEO_DAS_MATCH_MARGIN_SECONDS
from utils.function import printError


class VideoFilesController(WindowFeature):
    """Video-time matching and metadata-only BIN sequence loading."""

    def __init__(self, window):
        super().__init__(window)
        self.video_sequence_data_group = None
        self.video_sequence_timeline = None
        self.video_sequence_source_paths = []
        self.video_sequence_time_headers = []
        self.video_sequence_selected_segment_index = None
        self.video_das_match_required = False

    @staticmethod
    def _videoPeriod(value: datetime) -> str:
        hour = value.hour
        if 4 <= hour < 11:
            return "清晨"
        if 11 <= hour < 18:
            return "下午"
        return "夜间/凌晨"

    def _recommendedDasFolder(self, video_start: datetime):
        """Find a same-date BIN directory near the camera time without loading it."""
        current = getattr(self.window.data, "file_path", "")
        if not current or not os.path.isdir(current):
            return None
        search_root = os.path.dirname(os.path.normpath(current))
        groups = {}
        inspected = 0
        for directory, _subdirs, files in os.walk(search_root):
            for name in files:
                if not name.casefold().endswith(".bin"):
                    continue
                inspected += 1
                if inspected > 20_000:
                    break
                try:
                    value = parse_filename_end_time(name)
                except (TypeError, ValueError):
                    value = None
                if value is None or value.date() != video_start.date():
                    continue
                distance = abs((value - video_start).total_seconds())
                previous = groups.get(directory)
                groups[directory] = (
                    min(distance, previous[0]) if previous else distance,
                    (previous[1] if previous else 0) + 1,
                )
            if inspected > 20_000:
                break
        if not groups:
            return None
        directory, (distance, count) = min(groups.items(), key=lambda item: (item[1][0], -item[1][1], item[0]))
        return directory, count, distance

    def _refreshVideoDasRecommendation(self):
        """Show the likely DAS folder before the user starts time matching."""
        video_start = parse_video_start_time(self.window.annotations.video_annotation_project.video_path)
        _group, timeline = self.window.sync._videoDataContext()
        if video_start is None:
            return
        period = self._videoPeriod(video_start)
        folder_hint = self._recommendedDasFolder(video_start)
        folder_text = (
            f"文件夹 {os.path.basename(folder_hint[0])}（{folder_hint[1]} 个同日 BIN，最近约 {folder_hint[2]:.0f} s）"
            if folder_hint is not None
            else "当前数据根目录下未找到同日期 BIN 文件夹"
        )
        if timeline is None:
            self.window.sync.video_sync_summary_label.setText(
                f"录像时间 {video_start.date()} {period}；{folder_text}。点击“匹配 DAS”按时间范围载入。"
            )
            return
        das_date = timeline.start_time.date()
        if das_date != video_start.date():
            self.window.sync.video_sync_summary_label.setText(
                f"日期不匹配：录像为 {video_start.date()} {period}，当前 DAS 为 {das_date}。"
                f"推荐 {folder_text}；不会自动把 9 月 4 日数据当作 9 月 5 日对时。"
            )
            return
        self.window.sync.video_sync_summary_label.setText(
            f"推荐并已核对：{video_start.date()} {period} DAS，{folder_text}；可拖动右侧紫色虚线校正当前视频帧。"
        )

    def _videoSourceDurationMs(self) -> int:
        if self.window.playback.probe is not None and self.window.playback.probe.duration_seconds:
            return max(0, int(round(self.window.playback.probe.duration_seconds * 1000.0)))
        if self.window.playback.duration_ms > 0:
            return int(self.window.playback.duration_ms)
        return max(0, int(self.window.playback.position_slider.maximum()))

    def _videoWallTimeRange(self):
        """Return the calibrated source-video wall-clock interval."""

        sync = self.window.annotations.video_annotation_project.sync
        duration_ms = self._videoSourceDurationMs()
        start = sync.wall_time_for_video_position(0)
        end = sync.wall_time_for_video_position(duration_ms)
        if start is None:
            raise ValueError("无法从录像文件名识别开始时间，请先在标注页填写视频开始时间")
        if duration_ms <= 0 or end is None:
            raise ValueError("尚未取得录像时长，请等待媒体探测完成")
        return min(start, end), max(start, end)

    def _matchingVideoDasPaths(self, folder: str, margin_seconds: float = VIDEO_DAS_MATCH_MARGIN_SECONDS):
        """Match BIN files whose corrected acquisition interval overlaps the video."""

        folder = os.path.realpath(str(folder))
        if not os.path.isdir(folder):
            raise ValueError("DAS 文件夹不存在")
        video_start, video_end = self._videoWallTimeRange()
        margin = timedelta(seconds=max(0.0, float(margin_seconds)))
        wanted_start = video_start - margin
        wanted_end = video_end + margin
        matches = []
        for name in sorted(os.listdir(folder), key=natural_sort_key):
            if not name.casefold().endswith(".bin"):
                continue
            path = os.path.join(folder, name)
            try:
                header, samples, _channels, rate, _endian = read_bin_header(path)
                file_end = recorded_end_time(path, header[:6])[0] + timedelta(
                    seconds=self.window.controls.time_correction_seconds
                )
                file_start = file_end - timedelta(seconds=float(samples) / float(rate))
            except (OSError, TypeError, ValueError, ZeroDivisionError):
                continue
            if file_end >= wanted_start and file_start <= wanted_end:
                matches.append((file_start, path))
        return [path for _start, path in sorted(matches, key=lambda item: (item[0], natural_sort_key(item[1])))]

    def chooseVideoDasFolder(self):
        """Choose a DAS folder, time-match it to the video, and load metadata only."""

        try:
            video_start, _video_end = self._videoWallTimeRange()
        except ValueError as error:
            printError(str(error))
            return
        current = getattr(self.window.data, "file_path", "")
        hint = self._recommendedDasFolder(video_start)
        default_folder = hint[0] if hint is not None else current
        folder = QFileDialog.getExistingDirectory(self.window, "选择与录像对应的 DAS 文件夹", default_folder or "")
        if not folder:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.video_sequence_status_label.setText("匹配 DAS：正在扫描文件头…")
        QApplication.processEvents()
        try:
            paths = self._matchingVideoDasPaths(folder)
        finally:
            QApplication.restoreOverrideCursor()
        if not paths:
            start, end = self._videoWallTimeRange()
            message = f"所选文件夹中没有与录像 {format_wall_time(start)} 至 {format_wall_time(end)} 重叠的 BIN 文件"
            printError(message)
            self.video_sequence_status_label.setText("匹配 DAS：未找到重叠文件")
            return
        self.window.data.file_path = folder
        self.window.data.updateFile()
        self.loadVideoSequencePaths(paths, source_description="按录像时间匹配")

    def _videoSequencePathsFromStartRow(self, start_row: int):
        """Use one selected directory row as the start of a same-format sequence."""

        first = self.window.data.files_table_widget.item(int(start_row), 0)
        if first is None:
            return []
        suffix = self.window.data.dataFileSuffix(first.text())
        paths = []
        for row in range(int(start_row), self.window.data.files_table_widget.rowCount()):
            item = self.window.data.files_table_widget.item(row, 0)
            if item is None:
                continue
            if self.window.data.dataFileSuffix(item.text()) != suffix:
                continue
            paths.append(self.window.data.dataFilePath(item.text()))
        return paths

    @staticmethod
    def _videoSequenceWasCancelled(progress):
        return progress.wasCanceled() if progress is not None else False

    def loadVideoSequenceFromStartRow(self, start_row: int):
        """Compatibility entry point: build metadata from the selected row onward."""

        paths = self._videoSequencePathsFromStartRow(start_row)
        if not paths:
            printError("未找到可连续读取的 DAS 文件")
            return
        self.loadVideoSequencePaths(paths, source_description="从所选文件开始")

    def loadVideoSequencePaths(self, paths, source_description="按录像时间匹配"):
        """Build a continuous video/DAS timeline from headers without reading payloads."""

        paths = [os.path.realpath(str(path)) for path in paths]
        if not paths:
            printError("没有可载入的视频 DAS 文件")
            return
        progress = QProgressDialog("正在读取 DAS 文件头…", "取消", 0, len(paths), self.window)
        progress.setWindowTitle("匹配视频与 DAS")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(True)
        progress.setValue(0)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

        try:
            validate_bin_paths(paths)
            headers = []
            sample_counts = []
            channels_num = None
            sampling_rate = None
            for index, path in enumerate(paths):
                if self._videoSequenceWasCancelled(progress):
                    raise RuntimeError("已取消视频 DAS 载入")
                header, samples, channels, rate, _endian = read_bin_header(path)
                header = tuple(map(float, header[:6]))
                if channels_num is None:
                    channels_num, sampling_rate = int(channels), float(rate)
                elif channels != channels_num or not np.isclose(rate, sampling_rate):
                    raise ValueError(f"{path}: 通道数或采样率与首个文件不一致，载入已停止")
                headers.append(header)
                sample_counts.append(int(samples))
                progress.setLabelText(f"正在读取时间轴：{index + 1}/{len(paths)}")
                progress.setValue(index + 1)
                QApplication.processEvents()

            data_group = DataGroup.from_files(paths, sample_counts, channels_num, sampling_rate)
            timeline = DataTimeline.from_data_group(
                data_group,
                headers,
                correction_seconds=self.window.controls.time_correction_seconds,
            )
            self.video_sequence_data_group = data_group
            self.video_sequence_timeline = timeline
            self.video_sequence_source_paths = list(paths)
            self.video_sequence_time_headers = list(headers)
            self.video_sequence_selected_segment_index = 0
            self.video_das_match_required = False
            self.window.video_analysis._ensureDefaultVideoFilterPipeline(
                int(channels_num), int(data_group.total_samples)
            )
            if self.window.annotations.video_annotation_project.camera_channel > channels_num:
                self.window.annotations.video_annotation_project.set_camera_channel(int(channels_num))
            self.window.sync.updateVideoAnnotationDataContext()
            self.window.sync._syncVideoProjectWidgets()
            self._refreshVideoDasRecommendation()
            self.window.video_analysis._configureVideoTrajectoryAnalysis()
            self.window.annotations.refreshVideoAnnotationTable(
                select_identifier=self.window.annotations.video_annotation_selected_id
            )
            self.video_sequence_status_label.setText(f"匹配 DAS：{len(paths)} 文件 · 播放时按窗口读取")
            self.video_sequence_status_label.setToolTip(
                f"{source_description}：{os.path.basename(paths[0])} 至 {os.path.basename(paths[-1])}；"
                f"仅载入文件头和 {timeline.total_samples} 点时间轴，原始数据随播放位置读取。"
            )
            self.window.video_plot.plotVideoComparisonImage()
            self.window.workspace.tab_widget.setCurrentWidget(self.window.video_ui.video_compare_container)
            self.window.statusBar().showMessage(
                f"视频 DAS 已就绪：匹配 {len(paths)} 个文件，播放时按窗口读取。",
                10000,
            )
        except Exception as error:
            printError(error)
            self.window.statusBar().showMessage(f"视频 DAS 载入失败：{error}", 10000)
        finally:
            progress.close()
            QApplication.restoreOverrideCursor()

    def rebuildVideoSequenceTimeline(self):
        """Apply the same DAS clock correction to a metadata-only video sequence."""

        if self.video_sequence_data_group is None or not self.video_sequence_time_headers:
            return
        self.video_sequence_timeline = DataTimeline.from_data_group(
            self.video_sequence_data_group,
            self.video_sequence_time_headers,
            correction_seconds=self.window.controls.time_correction_seconds,
        )
