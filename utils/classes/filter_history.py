"""Persistent, validated filter-chain history records."""

from __future__ import annotations

import json
from datetime import datetime
from math import isfinite
from typing import Dict, Iterable, List, Sequence
from uuid import uuid4

from .filter_pipeline import FilterStep


HISTORY_SCHEMA_VERSION = 1
MAX_RECENT_PIPELINES = 10


def history_entry_steps(entry: Dict[str, object]) -> List[FilterStep]:
    """Deserialize a history entry into independent filter steps."""

    values = entry.get("steps", [])
    if not isinstance(values, list):
        raise ValueError("滤波方案步骤格式无效")
    steps = [FilterStep.from_dict(value) for value in values if isinstance(value, dict)]
    if len(steps) != len(values) or not steps:
        raise ValueError("滤波方案不包含有效步骤")
    return steps


def pipeline_signature(steps: Iterable[FilterStep]) -> str:
    """Return a stable semantic signature that ignores generated step IDs."""

    payload = []
    for step in steps:
        payload.append({
            "algorithm": step.algorithm,
            "parameters": step.parameters,
            "selection": list(step.selection),
            "enabled": bool(step.enabled),
            "processing_mode": step.processing_mode,
        })
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def make_history_entry(
    name: str,
    kind: str,
    steps: Iterable[FilterStep],
    source_shape: Sequence[int],
    sampling_rate: float,
) -> Dict[str, object]:
    """Build one JSON-compatible history record."""

    clean_name = str(name).strip()
    if not clean_name:
        raise ValueError("滤波方案名称不能为空")
    if kind not in {"named", "recent"}:
        raise ValueError("滤波方案类型无效")
    shape = tuple(map(int, source_shape))
    if len(shape) != 2 or min(shape) <= 0:
        raise ValueError("滤波方案源数据尺寸无效")
    rate = float(sampling_rate)
    if not isfinite(rate) or rate <= 0:
        raise ValueError("滤波方案采样率无效")
    serialized_steps = [step.to_dict() for step in steps]
    if not serialized_steps:
        raise ValueError("空滤波链不能保存")
    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "identifier": uuid4().hex,
        "name": clean_name,
        "kind": kind,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "source_shape": list(shape),
        "sampling_rate": rate,
        "steps": serialized_steps,
    }


def normalize_history(entries) -> List[Dict[str, object]]:
    """Drop corrupt records so malformed preferences never block startup."""

    if not isinstance(entries, list):
        return []
    normalized: List[Dict[str, object]] = []
    identifiers = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            identifier = str(entry.get("identifier", "")).strip()
            name = str(entry.get("name", "")).strip()
            kind = str(entry.get("kind", ""))
            saved_at = str(entry.get("saved_at", "")).strip()
            shape = tuple(map(int, entry.get("source_shape", ())))
            rate = float(entry.get("sampling_rate", 0.0))
            steps = history_entry_steps(entry)
            if (
                int(entry.get("schema_version", 0)) != HISTORY_SCHEMA_VERSION
                or not identifier
                or identifier in identifiers
                or not name
                or kind not in {"named", "recent"}
                or not saved_at
                or len(shape) != 2
                or min(shape) <= 0
                or not isfinite(rate)
                or rate <= 0
            ):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        identifiers.add(identifier)
        normalized.append({
            "schema_version": HISTORY_SCHEMA_VERSION,
            "identifier": identifier,
            "name": name,
            "kind": kind,
            "saved_at": saved_at,
            "source_shape": list(shape),
            "sampling_rate": rate,
            "steps": [step.to_dict() for step in steps],
        })
    named = [entry for entry in normalized if entry["kind"] == "named"]
    recent = [entry for entry in normalized if entry["kind"] == "recent"][:MAX_RECENT_PIPELINES]
    return named + recent


def upsert_named_history(entries, new_entry: Dict[str, object]) -> List[Dict[str, object]]:
    """Insert a named scheme, replacing a same-name scheme case-insensitively."""

    normalized = normalize_history(entries)
    clean = normalize_history([new_entry])
    if not clean or clean[0]["kind"] != "named":
        raise ValueError("要保存的命名滤波方案无效")
    candidate = clean[0]
    name_key = str(candidate["name"]).casefold()
    remaining = [
        entry for entry in normalized
        if entry["kind"] != "named" or str(entry["name"]).casefold() != name_key
    ]
    named = [entry for entry in remaining if entry["kind"] == "named"]
    recent = [entry for entry in remaining if entry["kind"] == "recent"]
    return [candidate] + named + recent


def add_recent_history(entries, new_entry: Dict[str, object]) -> List[Dict[str, object]]:
    """Remember a confirmed chain, deduplicated by processing semantics."""

    normalized = normalize_history(entries)
    clean = normalize_history([new_entry])
    if not clean or clean[0]["kind"] != "recent":
        raise ValueError("要保存的最近滤波链无效")
    candidate = clean[0]
    signature = pipeline_signature(history_entry_steps(candidate))
    named = [entry for entry in normalized if entry["kind"] == "named"]
    recent = [
        entry for entry in normalized
        if entry["kind"] == "recent"
        and pipeline_signature(history_entry_steps(entry)) != signature
    ]
    return named + [candidate] + recent[:MAX_RECENT_PIPELINES - 1]
