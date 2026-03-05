# src/ipc.py
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    """
    Atomic JSON write: write to temp file then replace.
    Prevents UI reading half-written JSON.
    """
    folder = os.path.dirname(path)
    if folder:
        _ensure_dir(folder)

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def read_json(path: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        # If UI reads during write (shouldn't happen with atomic replace),
        # fall back safely.
        return default


@dataclass
class IPCPaths:
    control_path: str = "settings/ipc/control.json"
    status_path: str = "settings/ipc/status.json"


def default_control() -> Dict[str, Any]:
    return {
        "command": "NONE",          # START/STOP/PAUSE/CONTINUE/RESTART/NONE
        "program": None,            # program name when relevant
        "issued_at": time.time(),
        "command_id": 0,            # monotonic int set by UI
    }


def default_status() -> Dict[str, Any]:
    return {
        "state": "IDLE",            # IDLE/RUNNING/PAUSED/ERROR
        "program": None,
        "process": "not running",   # mixing/moving/cutting wire/doing PEO/...
        "iteration": {"i": 0, "n": 0},
        "params": {
            "Upos": None,
            "PEO_time": None,
            "KOH_target": None,
        },
        "fluid": {
            "total_ml": None,
            "ratios": {},            # e.g. {"KOH_stock": 0.3, "H2O": 0.7}
            "channels": {},          # e.g. {"CH1": 0.7, "CH2": 0.3}
        },
        "last_event": "",
        "error": None,
        "updated_at": time.time(),
        "seen_command_id": 0,       # last processed command_id
    }