from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class SupervisorCommand:
    action: str
    payload: dict


class CommandBridge:
    """
    Simple file-based command inbox for the UI.
    The UI writes one command JSON file.
    The runtime consumes it once and then removes it.
    """

    def __init__(self, command_path: str = "settings/ui_command.json") -> None:
        self.command_path = command_path
        os.makedirs(os.path.dirname(command_path), exist_ok=True)

    def read_once(self) -> Optional[SupervisorCommand]:
        if not os.path.exists(self.command_path):
            return None

        try:
            with open(self.command_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        finally:
            try:
                os.remove(self.command_path)
            except FileNotFoundError:
                pass

        action = str(raw.get("action", "")).strip().lower()
        payload = dict(raw.get("payload", {}))

        if not action:
            return None

        return SupervisorCommand(action=action, payload=payload)

    def write_command(self, action: str, payload: Optional[dict] = None) -> None:
        data = {
            "action": action,
            "payload": payload or {},
        }
        tmp = self.command_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.command_path)