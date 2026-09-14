"""Small typed wrapper around persistent DASViewer user preferences."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QSettings


class AppPreferences:
    TIME_CORRECTION_KEY = "timeline/device_behind_seconds"
    AUTO_FILTER_KEY = "filter/auto_reapply_pipeline"

    def __init__(self, settings: Optional[QSettings] = None):
        self.settings = settings or QSettings("DASViewer", "DASViewer")

    def time_correction_seconds(self) -> float:
        value = self.settings.value(self.TIME_CORRECTION_KEY, 12.0)
        try:
            return min(max(float(value), -86400.0), 86400.0)
        except (TypeError, ValueError):
            return 12.0

    def set_time_correction_seconds(self, value: float) -> None:
        self.settings.setValue(self.TIME_CORRECTION_KEY, float(value))
        self.settings.sync()

    def auto_reapply_filter(self) -> bool:
        value = self.settings.value(self.AUTO_FILTER_KEY, True)
        if isinstance(value, bool):
            return value
        return str(value).strip().casefold() in {"1", "true", "yes", "on"}

    def set_auto_reapply_filter(self, enabled: bool) -> None:
        self.settings.setValue(self.AUTO_FILTER_KEY, bool(enabled))
        self.settings.sync()
