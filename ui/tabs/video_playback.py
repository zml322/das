"""Standalone video loading, transport controls and compatible FFmpeg playback."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PyQt5 import QtMultimedia
from PyQt5.QtCore import QEvent, Qt, QTimer, QUrl
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFileDialog

from core.video.media import cached_playable_video, probe_video
from core.video.player import FfmpegFrameWorker
from ui.components.window_feature import WindowFeature


def format_position(milliseconds):
    seconds, millis = divmod(max(0, int(milliseconds)), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


class VideoPlaybackController(WindowFeature):
    def __init__(self, window):
        super().__init__(window)
        self.qt_player = None
        self.source_path = None
        self.playback_path = None
        self.backend = "qt"
        self.worker = None
        self.position_ms = 0
        self.duration_ms = 0
        self.playing = False
        self.slider_dragging = False
        self.frame_pixmap = None
        self.conversion_future = None
        self.conversion_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="das-video-transcode")
        self.conversion_timer = QTimer(self)
        self.conversion_timer.setInterval(250)
        self.conversion_timer.timeout.connect(self._pollConversion)

    def initializePlayer(self, surface):
        """Attach the optional Qt output after the layout has created it."""
        if surface is None:
            return
        self.qt_player = QtMultimedia.QMediaPlayer(self)
        self.qt_player.setVideoOutput(surface)
        self.qt_player.positionChanged.connect(self._positionChanged)
        self.qt_player.durationChanged.connect(self._durationChanged)
        self.qt_player.stateChanged.connect(self._stateChanged)
        self.qt_player.mediaStatusChanged.connect(self._mediaStatusChanged)
        self.qt_player.error.connect(self._playerError)

    def chooseFile(self):
        path, _ = QFileDialog.getOpenFileName(
            self.window,
            "选择视频",
            "",
            "视频文件 (*.mp4 *.mov *.avi *.mkv *.mpeg *.mpg *.m4v);;所有文件 (*.*)",
        )
        if path:
            self.loadFile(path)

    def loadFile(self, path):
        """Load media without touching DAS data or automatically starting playback."""
        self.stopWorker()
        self.conversion_timer.stop()
        if self.conversion_future is not None:
            self.conversion_future.cancel()
            self.conversion_future = None
        if self.qt_player is not None:
            self.qt_player.stop()
            self.qt_player.setMedia(QtMultimedia.QMediaContent())
        self.source_path = str(path)
        self.playback_path = self.source_path
        self.backend = "qt"
        self.position_ms = self.duration_ms = 0
        self.playing = self.slider_dragging = False
        self.frame_pixmap = None
        self.frame_surface.clear()
        self.source_label.setText(Path(path).name)
        self.source_label.setToolTip(self.source_path)
        self.play_button.setText("播放")
        self.position_slider.setRange(0, 0)
        self._updateTime()
        self._setControlsEnabled(False)
        try:
            probe = probe_video(path)
        except (OSError, ValueError) as error:
            self.status_label.setText(f"视频加载失败：{error}")
            return
        if probe.is_mpeg_program_stream or self.qt_player is None:
            self.backend = "ffmpeg"
            self.viewport_stack.setCurrentWidget(self.frame_surface)
            self.frame_surface.setText("正在准备兼容播放缓存…")
            self.status_label.setText("正在后台准备视频…")
            self.conversion_future = self.conversion_executor.submit(cached_playable_video, self.source_path)
            self.conversion_timer.start()
        else:
            self.viewport_stack.setCurrentWidget(self.surface)
            self.status_label.setText("正在加载视频…")
            self.qt_player.setMedia(QtMultimedia.QMediaContent(QUrl.fromLocalFile(self.source_path)))

    def _pollConversion(self):
        future = self.conversion_future
        if future is None or not future.done():
            return
        self.conversion_future = None
        self.conversion_timer.stop()
        try:
            self._loadFfmpegVideo(str(future.result()))
        except (OSError, ValueError, RuntimeError) as error:
            self.status_label.setText(f"播放缓存生成失败：{error}")

    def _loadFfmpegVideo(self, path):
        self.stopWorker()
        self.backend = "ffmpeg"
        self.playback_path = str(path)
        self.duration_ms = int(round((probe_video(path).duration_seconds or 0) * 1000))
        self.position_ms = 0
        self.viewport_stack.setCurrentWidget(self.frame_surface)
        self.position_slider.setRange(0, self.duration_ms)
        self._setControlsEnabled(True)
        self.status_label.setText("视频已载入")
        self._seekFfmpeg(0, False)

    def _setControlsEnabled(self, enabled):
        for widget in (self.play_button, self.back_button, self.forward_button, self.speed_combo, self.position_slider):
            widget.setEnabled(enabled)

    def togglePlayback(self):
        if not self.play_button.isEnabled():
            return
        if self.backend == "ffmpeg":
            if self.playing:
                self.stopWorker()
                self._setPlaying(False)
            else:
                position = 0 if self.position_ms >= self.duration_ms else self.position_ms
                self._seekFfmpeg(position, True)
        elif self.qt_player.state() == QtMultimedia.QMediaPlayer.PlayingState:
            self.qt_player.pause()
        else:
            if self.qt_player.position() >= self.qt_player.duration():
                self.qt_player.setPosition(0)
            self.qt_player.play()

    def seekBy(self, delta):
        self.seek(self.position_ms + int(delta))

    def seek(self, position):
        if not self.position_slider.isEnabled():
            return
        target = min(max(0, int(position)), self.duration_ms)
        if self.backend == "ffmpeg":
            self._seekFfmpeg(target, self.playing)
        else:
            self.qt_player.setPosition(target)

    def setPlaybackRate(self, _index):
        rate = float(self.speed_combo.currentData())
        if self.backend == "ffmpeg":
            if self.playing:
                self._seekFfmpeg(self.position_ms, True)
        elif self.qt_player is not None:
            self.qt_player.setPlaybackRate(rate)

    def sliderPressed(self):
        self.slider_dragging = True

    def sliderMoved(self, position):
        self._updateTime(position)

    def sliderReleased(self):
        self.slider_dragging = False
        self.seek(self.position_slider.value())

    def _seekFfmpeg(self, position, play):
        self.stopWorker()
        self.position_ms = min(max(0, int(position)), self.duration_ms)
        self._setPlaying(play)
        self.worker = FfmpegFrameWorker(
            self.playback_path,
            self.position_ms,
            playback_rate=float(self.speed_combo.currentData()),
            play_continuously=play,
            parent=self,
        )
        self.worker.frameReady.connect(self._frameReady)
        self.worker.playbackEnded.connect(self._playbackEnded)
        self.worker.errorRaised.connect(self._workerError)
        self.worker.start()

    def _frameReady(self, image, position):
        if self.sender() is not self.worker:
            return
        self.frame_pixmap = QPixmap.fromImage(image)
        self._renderFrame()
        self._positionChanged(position)

    def _renderFrame(self):
        if self.frame_pixmap is not None:
            self.frame_surface.setPixmap(
                self.frame_pixmap.scaled(
                    self.frame_surface.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

    def eventFilter(self, watched, event):
        if watched is self.frame_surface and event.type() == QEvent.Resize:
            QTimer.singleShot(0, self._renderFrame)
        return super().eventFilter(watched, event)

    def _positionChanged(self, position):
        if self.sender() is self.qt_player and self.backend != "qt":
            return
        self.position_ms = max(0, int(position))
        if not self.slider_dragging:
            self.position_slider.setValue(self.position_ms)
            self._updateTime()

    def _durationChanged(self, duration):
        if self.backend == "qt":
            self.duration_ms = max(0, int(duration))
            self.position_slider.setRange(0, self.duration_ms)
            self._updateTime()

    def _stateChanged(self, state):
        if self.backend == "qt":
            self._setPlaying(state == QtMultimedia.QMediaPlayer.PlayingState)

    def _setPlaying(self, playing):
        self.playing = playing
        self.play_button.setText("暂停" if playing else "播放")

    def _updateTime(self, position=None):
        self.time_label.setText(
            f"{format_position(self.position_ms if position is None else position)} / "
            f"{format_position(self.duration_ms)}"
        )

    def _mediaStatusChanged(self, status):
        if self.backend != "qt":
            return
        if status == QtMultimedia.QMediaPlayer.LoadedMedia:
            self.qt_player.setPlaybackRate(float(self.speed_combo.currentData()))
            self._setControlsEnabled(True)
            self.status_label.setText("视频已载入")
        elif status == QtMultimedia.QMediaPlayer.InvalidMedia:
            self._playerError()

    def _playerError(self, *_args):
        if self.backend == "qt":
            self._setControlsEnabled(False)
            self._setPlaying(False)
            self.status_label.setText(f"视频播放失败：{self.qt_player.errorString().strip()}")

    def _workerError(self, message):
        if self.sender() is self.worker:
            self._setPlaying(False)
            self.status_label.setText(f"视频播放失败：{message}")

    def _playbackEnded(self):
        if self.sender() is self.worker:
            if self.playing:
                self._positionChanged(self.duration_ms)
            self._setPlaying(False)

    def stopWorker(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.stop()
            worker.wait(3000)

    def shutdown(self):
        self.conversion_timer.stop()
        self.stopWorker()
        if self.qt_player is not None:
            self.qt_player.stop()
        self.conversion_executor.shutdown(wait=False, cancel_futures=True)
