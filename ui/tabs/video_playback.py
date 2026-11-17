"""Qt and FFmpeg video playback, conversion and transport controls."""

import os.path
from concurrent.futures import Future, ThreadPoolExecutor

from PyQt5 import QtMultimedia
from PyQt5.QtCore import QEvent, Qt, QTimer, QUrl
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFileDialog

from core.video.annotation import format_video_position, parse_video_start_time
from core.video.media import cached_playable_video, probe_video
from core.video.player import FfmpegFrameWorker
from ui.components.window_feature import WindowFeature

try:
    from PyQt5.QtMultimediaWidgets import QVideoWidget
except ImportError:
    QVideoWidget = None


class VideoPlaybackController(WindowFeature):
    """Qt and FFmpeg video playback, conversion and transport controls."""

    def __init__(self, window):
        super().__init__(window)
        self.slider_dragging = False
        self.qt_player = None
        self.probe = None
        self.playback_path = None
        self.conversion_future: Future | None = None
        self.conversion_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="das-video-transcode")
        self.conversion_timer = QTimer(self)
        self.conversion_timer.setInterval(250)
        self.conversion_timer.timeout.connect(self._pollVideoMediaConversion)
        self.backend = "qt"
        self.worker = None
        self.duration_ms = 0
        self.position_ms = 0
        self.playing = False
        self.frame_pixmap = None

    def shutdown(self):
        """Release playback resources owned by this controller."""
        self.conversion_timer.stop()
        self._stopFfmpegVideoWorker()
        if self.qt_player is not None:
            self.qt_player.stop()
        self.conversion_executor.shutdown(wait=False, cancel_futures=True)

    def chooseVideoComparisonFile(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window,
            "选择摄像头视频",
            "",
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.mpeg *.mpg *.m4v);;所有文件 (*.*)",
        )
        if path:
            self.loadVideoComparisonFile(path)

    def loadVideoComparisonFile(self, path: str, update_project: bool = True):
        """Set source media and use a local truthful-suffix cache only if needed."""

        path = str(path)
        # 加载新视频时清除正在进行的区间标注
        self.window.annotations._cancelPendingIntervalAnnotation()
        self.window.sync._clearVideoSequenceContext()
        if update_project:
            parsed_start = parse_video_start_time(path)
            self.window.annotations.video_annotation_project.video_path = path
            self.window.annotations.video_annotation_project.sync.update(parsed_start, 0.0, 1.0)
            self.window.annotations.video_annotation_project.calibration_anchors = []
            self.window.sync.video_sync_calibration_anchors = []
            self.window.sync._video_sync_undo_stack.clear()
            self.window.sync._finishVideoSyncPick()
            self.window.sync._markVideoAnnotationDirty()
            if parsed_start is None:
                self.window.sync.video_sync_hint_label.setText("未能从文件名识别开始时间，请手工填写视频开始时间。")
            else:
                self.window.sync.video_sync_hint_label.setText("文件名时间作为初始值；可拖动紫色虚线对准同一车辆事件。")
        self.window.video_files.video_das_match_required = True
        if hasattr(self.window.workspace, "sidebar_tabs"):
            self.window.workspace.sidebar_tabs.setCurrentWidget(self.window.video_ui.annotation_sidebar_widget)
        self.source_label.setText(f"视频：{os.path.basename(path)}")
        self.source_label.setToolTip(path)
        self._stopFfmpegVideoWorker()
        self.frame_pixmap = None
        self.backend = "qt"
        self.viewport_stack.setCurrentWidget(self.surface)
        self.playback_path = path
        self.probe = None
        conversion_pending = False
        try:
            probe = probe_video(path)
            self.probe = probe
            if probe.is_mpeg_program_stream:
                duration = format_video_position(int(round((probe.duration_seconds or 0.0) * 1000)))
                codec = probe.video_codec if probe.video_codec != "unknown" else "视频编码待媒体后端确认"
                completion = {
                    "terminated": "检测到节目流结束码",
                    "truncated_or_unfinalized": "未检测到结束码；固定容量零填充，不能视为完整",
                    "unfinalized": "未检测到节目流结束码，完整性无法确认",
                }.get(probe.completion_state, "完整性未知")
                self.media_info_label.setText(f"媒体探测：MPEG-PS · {codec} · PTS 时长 {duration} · {completion}")
                self.media_info_label.setToolTip(
                    f"只读源：{path}\n有效负载末尾：{probe.payload_end_offset:,} B；"
                    f"零填充：{probe.trailing_zero_bytes:,} B。播放使用本机独立 .mpg 缓存副本。"
                )
                self._startVideoMediaConversion(path)
                conversion_pending = True
            else:
                duration = format_video_position(int(round((probe.duration_seconds or 0.0) * 1000)))
                self.media_info_label.setText(f"媒体：{probe.video_codec} · {duration}")
                self.media_info_label.setToolTip("源文件格式由系统媒体后端直接播放。")
        except (OSError, ValueError) as error:
            self.media_info_label.setText(f"媒体探测失败：{error}")
        self.window.video_files._refreshVideoDasRecommendation()
        self.window.sync._syncVideoProjectWidgets()
        if conversion_pending:
            if self.qt_player is not None:
                self.qt_player.stop()
                self.qt_player.setMedia(QtMultimedia.QMediaContent())
            for control in (
                self.play_button,
                self.back_button,
                self.forward_button,
                self.speed_combo,
            ):
                control.setEnabled(False)
            self.viewport_stack.setCurrentWidget(self.frame_surface)
            self.frame_surface.setText("正在生成独立播放缓存；源录像不会被修改。")
            self.position_slider.setRange(0, 0)
            self.time_label.setText("--:--:--.--- / --:--:--.---")
            self.window.sync._updateVideoPlayhead(0, force=True)
            self.window.video_plot.plotVideoComparisonImage()
            return
        if self.qt_player is None:
            self.window.sync.video_sync_summary_label.setText("当前 PyQt 安装没有可用的视频画面组件。")
            return
        self.qt_player.stop()
        self.qt_player.setMedia(QtMultimedia.QMediaContent(QUrl.fromLocalFile(self.playback_path)))
        self.position_slider.setRange(0, 0)
        self.time_label.setText("--:--:--.--- / --:--:--.---")
        self.window.sync._updateVideoPlayhead(0, force=True)
        self.window.video_plot.plotVideoComparisonImage()

    def _startVideoMediaConversion(self, source_path: str):
        """Transcode incompatible MPEG-PS in background, always into its cache."""
        expected_duration = self.probe.duration_seconds if self.probe is not None else None
        future = self.conversion_executor.submit(cached_playable_video, source_path, None, expected_duration)
        future._das_video_source_path = str(source_path)
        self.conversion_future = future
        self.conversion_timer.start()
        self.window.sync.video_sync_summary_label.setText(
            "正在后台生成 H.264/AAC 播放缓存；录像源保持只读，完成后可匹配 DAS。"
        )

    def _pollVideoMediaConversion(self):
        future = self.conversion_future
        if future is None or not future.done():
            return
        self.conversion_future = None
        self.conversion_timer.stop()
        try:
            playable_path = str(future.result())
        except Exception as error:
            self.window.sync.video_sync_summary_label.setText(f"播放缓存生成失败：{error}；源录像未被修改。")
            return
        if future._das_video_source_path != self.window.annotations.video_annotation_project.video_path:
            return
        self.playback_path = playable_path
        self._loadFfmpegVideo(playable_path)
        for control in (
            self.play_button,
            self.back_button,
            self.forward_button,
            self.speed_combo,
        ):
            control.setEnabled(True)
        source_duration = (
            int(round(self.probe.duration_seconds * 1000.0))
            if self.probe is not None and self.probe.duration_seconds
            else self.duration_ms
        )
        self.media_info_label.setText(
            "媒体探测：MPEG-PS 已转换为独立 H.264/AAC 播放缓存；"
            f"时间轴 {format_video_position(source_duration)}，已通过时长校验。"
        )
        self.window.sync.video_sync_summary_label.setText("播放缓存已就绪；可播放、跳转并与 DAS 同步。")

    def _loadFfmpegVideo(self, path: str):
        """Activate deterministic FFmpeg frame playback after cache conversion."""
        try:
            cache_probe = probe_video(path)
            self.duration_ms = int(round((cache_probe.duration_seconds or 0.0) * 1000.0))
        except (OSError, ValueError):
            self.duration_ms = 0
        self._stopFfmpegVideoWorker()
        self.backend = "ffmpeg"
        self.position_ms = 0
        self.position_slider.setRange(0, self.duration_ms)
        self.position_slider.setValue(0)
        self.window.sync._updateVideoTimeLabel(0, self.duration_ms)
        self.viewport_stack.setCurrentWidget(self.frame_surface)
        self.frame_surface.setText("播放缓存已就绪；点击播放。")
        self._seekFfmpegVideo(0, play_continuously=False)

    def _stopFfmpegVideoWorker(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.stop()
            worker.wait(500)

    def _seekFfmpegVideo(self, position_ms: int, play_continuously: bool):
        if not self.playback_path:
            return
        target = min(max(0, int(position_ms)), self.duration_ms)
        self._stopFfmpegVideoWorker()
        self.position_ms = target
        self.playing = bool(play_continuously)
        worker = FfmpegFrameWorker(
            self.playback_path,
            target,
            playback_rate=float(self.speed_combo.currentData() or 1.0),
            play_continuously=bool(play_continuously),
            parent=self,
        )
        worker.frameReady.connect(self._ffmpegVideoFrameReady)
        worker.playbackEnded.connect(self._ffmpegVideoEnded)
        worker.errorRaised.connect(lambda message: self.window.sync.video_sync_summary_label.setText(message))
        self.worker = worker
        worker.start()

    def _ffmpegVideoFrameReady(self, image, position_ms: int):
        if self.backend != "ffmpeg":
            return
        self.position_ms = min(max(0, int(position_ms)), self.duration_ms)
        pixmap = QPixmap.fromImage(image)
        if not pixmap.isNull():
            self.frame_pixmap = pixmap
            self._renderVideoFrame()
        if not self.slider_dragging:
            self.position_slider.setValue(self.position_ms)
        self.window.sync._updateVideoTimeLabel(self.position_ms, self.duration_ms)
        self.window.sync._updateVideoPlayhead(self.position_ms)

    def _renderVideoFrame(self):
        pixmap = self.frame_pixmap
        if pixmap is None or pixmap.isNull() or not hasattr(self, "frame_surface"):
            return
        mode = self.fit_combo.currentData() if hasattr(self, "fit_combo") else Qt.KeepAspectRatio
        self.frame_surface.setPixmap(
            pixmap.scaled(
                self.frame_surface.size(),
                mode,
                Qt.SmoothTransformation,
            )
        )

    def setVideoFitMode(self, _index: int):
        mode = self.fit_combo.currentData()
        if QVideoWidget is not None and isinstance(self.surface, QVideoWidget):
            self.surface.setAspectRatioMode(mode)
        self._renderVideoFrame()

    def eventFilter(self, watched, event):
        if (
            hasattr(self.window.video_ui, "annotation_sidebar_widget")
            and watched is self.window.video_ui.annotation_sidebar_widget
            and event.type() == QEvent.Resize
        ):
            # A small window gives more height to labels; a wide sidebar gives
            # the video its natural aspect ratio, within a modest height cap.
            height = min(
                240,
                max(
                    130,
                    int(min((watched.width() - 12) * 9 / 16, watched.height() * 0.22)),
                ),
            )
            if self.viewport.height() != height:
                self.viewport.setFixedHeight(height)
        if hasattr(self, "frame_surface") and watched is self.frame_surface and event.type() == QEvent.Resize:
            QTimer.singleShot(0, self._renderVideoFrame)
        return super().eventFilter(watched, event)

    def _ffmpegVideoEnded(self):
        if self.backend != "ffmpeg":
            return
        self.playing = False
        self.play_button.setText("播放")

    def toggleVideoPlayback(self):
        if self.window.annotations.annotation_canvas is not None and self.window.annotations.annotation_canvas.busy:
            self.window.annotations.annotation_canvas.cancel()
        if self.backend == "ffmpeg":
            if self.playing:
                self.playing = False
                self._stopFfmpegVideoWorker()
                self.play_button.setText("播放")
            else:
                self._seekFfmpegVideo(self.position_ms, play_continuously=True)
                self.play_button.setText("暂停")
            return
        if self.qt_player is None or not self.window.annotations.video_annotation_project.video_path:
            return
        if self.qt_player.state() == QtMultimedia.QMediaPlayer.PlayingState:
            self.qt_player.pause()
        else:
            self.qt_player.play()

    def seekVideoByMilliseconds(self, delta: int):
        if self.backend == "ffmpeg":
            self._seekFfmpegVideo(self.position_ms + int(delta), self.playing)
            return
        if self.qt_player is None:
            return
        maximum = max(0, self.qt_player.duration())
        target = min(max(0, self.qt_player.position() + int(delta)), maximum)
        self.qt_player.setPosition(target)
        self.window.sync._updateVideoPlayhead(target, force=True)

    def setVideoPlaybackRate(self, _index: int):
        if self.backend == "ffmpeg" and self.playing:
            self._seekFfmpegVideo(self.position_ms, play_continuously=True)
            return
        if self.qt_player is not None:
            self.qt_player.setPlaybackRate(float(self.speed_combo.currentData() or 1.0))

    def _videoSliderPressed(self):
        self.slider_dragging = True

    def _videoSliderMoved(self, value: int):
        self.window.sync._updateVideoTimeLabel(value, self.position_slider.maximum())
        self.window.sync._updateVideoPlayhead(value, force=True)

    def _videoSliderReleased(self):
        self.slider_dragging = False
        if self.backend == "ffmpeg":
            self._seekFfmpegVideo(self.position_slider.value(), self.playing)
            self.window.sync._updateVideoPlayhead(self.position_slider.value(), force=True)
            return
        if self.qt_player is not None:
            self.qt_player.setPosition(self.position_slider.value())
        self.window.sync._updateVideoPlayhead(self.position_slider.value(), force=True)

    def _videoDurationChanged(self, duration: int):
        if duration <= 0 and self.probe is not None and self.probe.duration_seconds:
            duration = int(round(self.probe.duration_seconds * 1000.0))
        self.position_slider.setRange(0, max(0, int(duration)))
        self.window.sync._updateVideoTimeLabel(
            self.qt_player.position() if self.qt_player else 0,
            duration,
        )

    def _videoStateChanged(self, state):
        self.play_button.setText("暂停" if state == QtMultimedia.QMediaPlayer.PlayingState else "播放")

    def _videoMediaStatusChanged(self, status):
        if status == QtMultimedia.QMediaPlayer.LoadedMedia:
            playback = "MPEG-PS 缓存副本" if self.probe and self.probe.is_mpeg_program_stream else "源文件"
            self.window.sync.video_sync_summary_label.setText(
                f"视频已载入（{playback}）；当前时间会同步到下方 DAS 竖线。"
            )
        elif status == QtMultimedia.QMediaPlayer.InvalidMedia:
            self.window.sync.video_sync_summary_label.setText(
                "当前 Windows 媒体后端仍无法播放该编码；源文件未被修改。"
                "请安装可用的 FFmpeg 后端或使用兼容的 H.264/AAC 缓存转码。"
            )

    def _videoPlayerError(self, *_args):
        if self.qt_player is not None:
            details = self.qt_player.errorString().strip()
            if details:
                self.window.sync.video_sync_summary_label.setText(f"视频播放失败：{details}")
