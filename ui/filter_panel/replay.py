"""在后台线程里从原始数据重放整条滤波链。"""

import traceback

import numpy as np
from PyQt5.QtCore import QObject, QThread, pyqtSignal

from core.filter.algorithms import apply_das_filter
from core.filter.filter_pipeline import clone_steps, replay_filter_pipeline


class _Worker(QThread):
    resultReady = pyqtSignal(object)
    errorRaised = pyqtSignal(str)

    def __init__(self, raw_data, sampling_rate, steps, segment_ranges, parent=None):
        super().__init__(parent)
        self._raw_data = np.asarray(raw_data, dtype=np.float32).copy()
        self._sampling_rate = float(sampling_rate)
        self._steps = clone_steps(steps)
        self._segment_ranges = list(segment_ranges)

    def run(self) -> None:
        try:
            result = replay_filter_pipeline(
                self._raw_data, self._sampling_rate, self._steps,
                apply_das_filter, self._segment_ranges,
            )
        except Exception:
            self.errorRaised.emit(traceback.format_exc())
        else:
            self.resultReady.emit(result)


class ReplayRunner(QObject):
    """一次只跑一个任务。结果依次发出 done/failed，线程结束后发 finished。"""

    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def start(self, raw_data, sampling_rate, steps, segment_ranges) -> None:
        worker = _Worker(raw_data, sampling_rate, steps, segment_ranges, parent=self)
        worker.resultReady.connect(self.done)
        worker.errorRaised.connect(self.failed)
        worker.finished.connect(self._on_finished)
        self._worker = worker
        worker.start()

    def _on_finished(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.deleteLater()
        self.finished.emit()
