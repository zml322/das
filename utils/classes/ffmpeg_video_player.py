"""Small FFmpeg frame player used when Windows Media Foundation rejects video."""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage

from .video_media import PLAYBACK_CACHE_FRAME_RATE, bundled_ffmpeg_executable


class FfmpegFrameWorker(QThread):
    """Decode a cache file into display frames without touching its source."""

    frameReady = pyqtSignal(QImage, int)
    playbackEnded = pyqtSignal()
    errorRaised = pyqtSignal(str)

    def __init__(
        self,
        path: str,
        start_ms: int,
        playback_rate: float = 1.0,
        play_continuously: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.path = str(Path(path))
        self.start_ms = max(0, int(start_ms))
        self.playback_rate = max(0.1, float(playback_rate))
        self.play_continuously = bool(play_continuously)
        self._stop = threading.Event()
        self._process = None
        self._process_lock = threading.Lock()
        # Camera recordings are 1280x720.  Decode at a bounded 16:9 display
        # resolution so background playback does not compete with DAS work.
        self.width, self.height, self.frame_rate = 960, 540, PLAYBACK_CACHE_FRAME_RATE

    def stop(self):
        self._stop.set()
        with self._process_lock:
            process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def run(self):
        frame_size = self.width * self.height * 3
        args = [
            bundled_ffmpeg_executable(), "-hide_banner", "-loglevel", "error",
            "-ss", f"{self.start_ms / 1000.0:.3f}", "-i", self.path, "-an",
            "-vf", f"scale={self.width}:{self.height}", "-pix_fmt", "rgb24",
            "-f", "rawvideo", "pipe:1",
        ]

        # Windows: 隐藏命令行窗口
        startupinfo = None
        if subprocess.os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        try:
            process = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                startupinfo=startupinfo
            )
        except OSError as error:
            self.errorRaised.emit(f"无法启动 FFmpeg 解码器：{error}")
            return
        with self._process_lock:
            self._process = process
        frame_index = 0
        frame_interval = 1.0 / (self.frame_rate * self.playback_rate)
        playback_started = time.monotonic()
        try:
            while not self._stop.is_set():
                raw = process.stdout.read(frame_size) if process.stdout is not None else b""
                if len(raw) != frame_size:
                    break
                position = self.start_ms + int(round(frame_index * 1000.0 / self.frame_rate))
                image = QImage(raw, self.width, self.height, self.width * 3, QImage.Format_RGB888).copy()
                self.frameReady.emit(image, position)
                if not self.play_continuously:
                    break
                frame_index += 1
                deadline = playback_started + frame_index * frame_interval
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    self._stop.wait(remaining)
        finally:
            with self._process_lock:
                self._process = None
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except (OSError, subprocess.SubprocessError):
                    pass
            if not self._stop.is_set():
                self.playbackEnded.emit()
