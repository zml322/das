"""The standalone video player's controls and expanding video surface."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ui.components.window_feature import WindowFeature
from ui.widgets.custom_widgets import ComboBox, PushButton

try:
    from PyQt5.QtMultimediaWidgets import QVideoWidget
except ImportError:
    QVideoWidget = None


class VideoLayoutController(WindowFeature):
    def createPage(self):
        player = self.window.playback
        self.video_container = QWidget()
        layout = QVBoxLayout(self.video_container)
        player.source_label = QLabel("未选择视频")
        layout.addWidget(player.source_label)

        player.load_button = PushButton("选择视频")
        player.play_button = PushButton("播放")
        player.back_button = PushButton("−1 s")
        player.forward_button = PushButton("+1 s")
        player.speed_combo = ComboBox()
        for rate in (0.25, 0.5, 1.0, 2.0):
            player.speed_combo.addItem(f"{rate:g}×", rate)
        player.speed_combo.setCurrentIndex(2)
        controls = QHBoxLayout()
        for widget in (
            player.load_button,
            player.play_button,
            player.back_button,
            player.forward_button,
            player.speed_combo,
        ):
            controls.addWidget(widget)
        controls.addStretch()
        layout.addLayout(controls)

        player.viewport = QWidget()
        player.viewport_stack = QStackedLayout(player.viewport)
        player.surface = QVideoWidget() if QVideoWidget is not None else None
        player.frame_surface = QLabel("选择视频后开始播放")
        player.frame_surface.setAlignment(Qt.AlignCenter)
        player.frame_surface.setMinimumSize(0, 0)
        player.frame_surface.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        player.frame_surface.installEventFilter(player)
        if player.surface is not None:
            player.viewport_stack.addWidget(player.surface)
        player.viewport_stack.addWidget(player.frame_surface)
        player.viewport_stack.setCurrentWidget(player.frame_surface)
        layout.addWidget(player.viewport, 1)

        player.position_slider = QSlider(Qt.Horizontal)
        player.position_slider.setRange(0, 0)
        player.position_slider.setAccessibleName("视频播放位置")
        player.time_label = QLabel("00:00:00.000 / 00:00:00.000")
        progress = QHBoxLayout()
        progress.addWidget(player.position_slider, 1)
        progress.addWidget(player.time_label)
        layout.addLayout(progress)
        player.status_label = QLabel("请选择视频")
        player.status_label.setWordWrap(True)
        layout.addWidget(player.status_label)

        player.load_button.clicked.connect(player.chooseFile)
        player.play_button.clicked.connect(player.togglePlayback)
        player.back_button.clicked.connect(lambda: player.seekBy(-1000))
        player.forward_button.clicked.connect(lambda: player.seekBy(1000))
        player.speed_combo.currentIndexChanged.connect(player.setPlaybackRate)
        player.position_slider.sliderPressed.connect(player.sliderPressed)
        player.position_slider.sliderMoved.connect(player.sliderMoved)
        player.position_slider.sliderReleased.connect(player.sliderReleased)
        player.initializePlayer(player.surface)
        player._setControlsEnabled(False)
        return self.video_container
