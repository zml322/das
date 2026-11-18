"""Application window composition and lifecycle orchestration."""

from PyQt5.QtWidgets import QApplication, QMainWindow

from configs.preferences import AppPreferences
from ui.components.data_controls import DataControlsController
from ui.components.plot_overlays import PlotOverlaysController
from ui.components.workspace import WorkspaceController
from ui.tabs.data_files import DataFilesController
from ui.tabs.data_plots import DataPlotsController
from ui.tabs.filtering import FilteringController
from ui.tabs.multi_waves import MultiWavesController
from ui.tabs.vehicle_analysis import VehicleAnalysisController
from ui.tabs.video_layout import VideoLayoutController
from ui.tabs.video_playback import VideoPlaybackController


class MainWindow(QMainWindow):
    """Compose independently owned feature controllers."""

    def __init__(self, preferences=None):
        super().__init__()
        self.preferences = preferences or AppPreferences()
        self.workspace = WorkspaceController(self)
        self.data = DataFilesController(self)
        self.controls = DataControlsController(self)
        self.plots = DataPlotsController(self)
        self.waves = MultiWavesController(self)
        self.overlays = PlotOverlaysController(self)
        self.vehicles = VehicleAnalysisController(self)
        self.filtering = FilteringController(self)
        self.video_ui = VideoLayoutController(self)
        self.playback = VideoPlaybackController(self)
        self.workspace.initMainWindow()
        self.plots.configurePlotDefaults()
        self.workspace.initUI()
        self.data.createMenu()
        self.controls.createMenu()
        self.plots.createMenu()
        self.filtering.createMenu()
        self.vehicles.createMenu()
        self.workspace.initLayout()
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def initLocalParams(self):
        self.data.resetRange()
        self.overlays.resetRange()
        self.waves.resetView()

    def updateImages(self):
        self.plots.plotGrayScaleImage()
        self.plots.plotSingleChannelTime()
        self.plots.plotAmplitudeFrequency()
        self.waves.plotMultiWavesImage()

    def updateAll(self):
        self.data.updateWidgetsState()
        self.data.updateFile()
        self.overlays.updateStitchedFilesList()
        self.data.updateDataRange()
        self.data.updateDataParams()
        self.data.updateDataGPSTime()
        self.updateImages()

    def closeEvent(self, event):
        self.workspace.closeEvent(event)

    def keyPressEvent(self, event):
        self.workspace.keyPressEvent(event)

    def shutdown(self):
        """Ask each feature to release its own resources."""
        self.playback.shutdown()
