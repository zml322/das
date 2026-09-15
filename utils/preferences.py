"""Small typed wrapper around persistent DASViewer user preferences."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Optional

from PyQt5.QtCore import QSettings


class AppPreferences:
    TIME_CORRECTION_KEY = "timeline/device_behind_seconds"
    AUTO_FILTER_KEY = "filter/auto_reapply_pipeline"
    FILTER_HISTORY_KEY = "filter/pipeline_history_v1"

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

    def filter_pipeline_history(self):
        """Return the JSON-compatible saved filter history, or an empty list."""

        value = self.settings.value(self.FILTER_HISTORY_KEY, "[]")
        if isinstance(value, list):
            return deepcopy(value)
        try:
            parsed = json.loads(str(value))
        except (TypeError, ValueError):
            return []
        return deepcopy(parsed) if isinstance(parsed, list) else []

    def set_filter_pipeline_history(self, entries) -> None:
        payload = json.dumps(list(entries), ensure_ascii=False, separators=(",", ":"))
        self.settings.setValue(self.FILTER_HISTORY_KEY, payload)
        self.settings.sync()
