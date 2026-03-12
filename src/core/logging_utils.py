from __future__ import annotations

import json
import os
from typing import Optional

from src.core.events import LogEvent


class EventLogger:
    def __init__(self, log_path: str = "settings/system_events.log") -> None:
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def emit(self, event: LogEvent) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def info(self, layer: str, device: str, command: str, result: str, detail: str = "", **extra) -> None:
        self.emit(LogEvent(layer=layer, device=device, command=command, result=result, detail=detail, extra=extra))

    def error(self, layer: str, device: str, command: str, detail: str = "", **extra) -> None:
        self.emit(LogEvent(layer=layer, device=device, command=command, result="ERROR", detail=detail, extra=extra))