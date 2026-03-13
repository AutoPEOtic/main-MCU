from __future__ import annotations

import json
import os
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any


def _jsonify(value: Any) -> Any:
    if is_dataclass(value):
        return {k: _jsonify(v) for k, v in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    return value


class RuntimeStore:
    """
    Writes the current runtime snapshot into JSON for the UI.
    """

    def __init__(self, snapshot_path: str = "settings/runtime_snapshot.json") -> None:
        self.snapshot_path = snapshot_path
        os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)

    def write_snapshot(self, snapshot: Any) -> None:
        data = _jsonify(snapshot)
        tmp = self.snapshot_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.snapshot_path)