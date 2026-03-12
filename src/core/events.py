from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict
import time


@dataclass
class LogEvent:
    layer: str
    device: str
    command: str
    result: str
    detail: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.ts,
            "layer": self.layer,
            "device": self.device,
            "command": self.command,
            "result": self.result,
            "detail": self.detail,
            "extra": self.extra,
        }