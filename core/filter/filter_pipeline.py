"""Editable, replayable filter history for two-dimensional DAS arrays."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from uuid import uuid4

import numpy as np


Selection = Tuple[int, int, int, int]
SegmentRange = Tuple[int, int]
FilterFunction = Callable[[np.ndarray, float, str, Dict[str, object]], np.ndarray]


@dataclass
class FilterStep:
    """One operation in an ordered filter history."""

    algorithm: str
    parameters: Dict[str, object]
    selection: Selection
    label: str
    enabled: bool = True
    processing_mode: str = "continuous"
    identifier: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        self.algorithm = str(self.algorithm)
        self.parameters = deepcopy(dict(self.parameters))
        self.selection = tuple(map(int, self.selection))  # type: ignore[assignment]
        if len(self.selection) != 4:
            raise ValueError("滤波范围必须包含起止通道和起止采样点")
        channel_from, channel_to, sample_from, sample_to = self.selection
        if channel_from < 1 or sample_from < 1 or channel_from > channel_to or sample_from > sample_to:
            raise ValueError("滤波步骤范围无效")
        if self.processing_mode not in {"continuous", "per_segment"}:
            raise ValueError("拼接处理方式只能是 continuous 或 per_segment")

    def clone(self, *, new_identifier: bool = False) -> "FilterStep":
        return FilterStep(
            algorithm=self.algorithm,
            parameters=deepcopy(self.parameters),
            selection=tuple(self.selection),
            label=self.label,
            enabled=bool(self.enabled),
            processing_mode=self.processing_mode,
            identifier=uuid4().hex if new_identifier else self.identifier,
        )

    def to_dict(self) -> Dict[str, object]:
        return {
            "algorithm": self.algorithm,
            "parameters": deepcopy(self.parameters),
            "selection": list(self.selection),
            "label": self.label,
            "enabled": bool(self.enabled),
            "processing_mode": self.processing_mode,
            "identifier": self.identifier,
        }

    @classmethod
    def from_dict(cls, value: Dict[str, object]) -> "FilterStep":
        return cls(
            algorithm=str(value["algorithm"]),
            parameters=deepcopy(dict(value.get("parameters", {}))),
            selection=tuple(value["selection"]),  # type: ignore[arg-type]
            label=str(value.get("label", value["algorithm"])),
            enabled=bool(value.get("enabled", True)),
            processing_mode=str(value.get("processing_mode", "continuous")),
            identifier=str(value.get("identifier") or uuid4().hex),
        )


class FilterPipeline:
    """Small mutable collection with safe cloning at its public boundary."""

    def __init__(self, steps: Optional[Iterable[FilterStep]] = None):
        self._steps = [step.clone() for step in (steps or [])]

    def __len__(self) -> int:
        return len(self._steps)

    def __iter__(self):
        return iter(self.steps())

    def steps(self) -> List[FilterStep]:
        return [step.clone() for step in self._steps]

    def add(self, step: FilterStep) -> None:
        self._steps.append(step.clone())

    def replace(self, index: int, step: FilterStep) -> None:
        self._steps[index] = step.clone()

    def remove(self, index: int) -> FilterStep:
        return self._steps.pop(index)

    def clear(self) -> None:
        self._steps.clear()

    def move(self, index: int, offset: int) -> int:
        destination = index + int(offset)
        if index < 0 or index >= len(self._steps) or destination < 0 or destination >= len(self._steps):
            return index
        step = self._steps.pop(index)
        self._steps.insert(destination, step)
        return destination

    def set_enabled(self, index: int, enabled: bool) -> None:
        self._steps[index].enabled = bool(enabled)


def clone_steps(steps: Iterable[FilterStep], *, new_identifiers: bool = False) -> List[FilterStep]:
    return [step.clone(new_identifier=new_identifiers) for step in steps]


def _validate_step_bounds(step: FilterStep, shape: Tuple[int, int]) -> None:
    channel_from, channel_to, sample_from, sample_to = step.selection
    if channel_to > shape[0] or sample_to > shape[1]:
        raise ValueError(
            f"滤波步骤“{step.label}”范围超出当前数据："
            f"通道 {channel_from}-{channel_to}，采样点 {sample_from}-{sample_to}，"
            f"当前数据为 {shape[0]} 通道、{shape[1]} 采样点。"
        )


def _step_sample_ranges(
    step: FilterStep,
    segment_ranges: Sequence[SegmentRange],
) -> List[SegmentRange]:
    selected_start = step.selection[2] - 1
    selected_end = step.selection[3]
    if step.processing_mode == "continuous" or not segment_ranges:
        return [(selected_start, selected_end)]

    intersections: List[SegmentRange] = []
    for segment_start, segment_end in segment_ranges:
        start = max(selected_start, int(segment_start))
        end = min(selected_end, int(segment_end))
        if start < end:
            intersections.append((start, end))
    return intersections


def replay_filter_pipeline(
    raw_data: np.ndarray,
    sampling_rate: float,
    steps: Iterable[FilterStep],
    filter_function: FilterFunction,
    segment_ranges: Optional[Sequence[SegmentRange]] = None,
) -> np.ndarray:
    """Replay enabled steps from an immutable baseline and return a new array."""

    baseline = np.asarray(raw_data, dtype=np.float32)
    if baseline.ndim != 2 or min(baseline.shape) <= 0:
        raise ValueError("滤波基线必须是非空二维数组")
    if not np.all(np.isfinite(baseline)):
        raise ValueError("滤波基线不能包含 NaN 或无穷值")

    working = baseline.copy()
    ranges = list(segment_ranges or [])
    for step in steps:
        if not step.enabled:
            continue
        _validate_step_bounds(step, working.shape)
        channel_from, channel_to, _sample_from, _sample_to = step.selection
        channel_slice = slice(channel_from - 1, channel_to)
        for sample_start, sample_end in _step_sample_ranges(step, ranges):
            data_slice = working[channel_slice, sample_start:sample_end]
            filtered = filter_function(
                data_slice,
                float(sampling_rate),
                step.algorithm,
                deepcopy(step.parameters),
            )
            filtered = np.asarray(filtered, dtype=np.float32)
            if filtered.shape != data_slice.shape:
                raise ValueError(f"滤波步骤“{step.label}”改变了数据形状")
            working[channel_slice, sample_start:sample_end] = filtered
    return working
