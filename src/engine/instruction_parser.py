from __future__ import annotations

import re
from typing import List

from src.core.errors import ValidationError
from src.engine.actions import (
    Action,
    DelayAction,
    HomeAction,
    MotionAction,
    MotionConfigAction,
    PEOOffAction,
    PEOOnAction,
    PEOSendValuesAction,
    PeripheralAction,
    ReconnectAction,
    SolutionAction,
    SpectrumAcquireAction,
)


_PERIPHERAL_TIMEOUTS = {
    "HOME": 180.0,
    "DEOXIDIZE": 180.0,
    "SOLUTION": 120.0,
    "FLUSH": 120.0,
    "CUT": 30.0,
}

_MOTION_RE = re.compile(r"^(G0|G1|G2|G3)\b", re.IGNORECASE)
_FEED_RE = re.compile(r"^F\s*-?\d+(\.\d+)?$", re.IGNORECASE)


def peripheral_timeout(command_upper: str) -> float:
    for prefix, timeout_s in _PERIPHERAL_TIMEOUTS.items():
        if command_upper.startswith(prefix):
            return timeout_s
    if command_upper.startswith("CH"):
        return 60.0
    return 30.0


def _clean_line(line: str) -> str:
    return line.split("#", 1)[0].strip()


def parse_instruction_line(line: str) -> Action | None:
    stripped = _clean_line(line)
    if not stripped:
        return None

    u = stripped.upper()

    # Explicit metadata / legacy no-op markers
    if u.startswith("LINE ONE"):
        return None

    if u.startswith("CHECKPOINT"):
        return None

    # Exact commands
    if u == "RECONNECT":
        return ReconnectAction(target="all")

    if u == "HOME":
        return HomeAction()

    if u == "SPECTRUM GET":
        return SpectrumAcquireAction()

    if u == "SEND PEO VALUES":
        return PEOSendValuesAction()

    if u == "PEO ON":
        return PEOOnAction(duration_s=-1.0)  # resolved later from run context

    if u == "PEO OFF":
        return PEOOffAction()

    if u == "SOLUTION":
        # actual channels are injected from run context later
        return SolutionAction(total_ml=-1.0, channels={})

    # PAUSE <value>
    if u.startswith("PAUSE"):
        parts = stripped.split()
        if len(parts) != 2:
            raise ValidationError(f"Invalid PAUSE syntax: '{line.strip()}'")
        try:
            seconds = float(parts[1]) / 10.0
        except ValueError as exc:
            raise ValidationError(f"Invalid PAUSE value: '{line.strip()}'") from exc
        if seconds < 0:
            raise ValidationError(f"PAUSE must be non-negative: '{line.strip()}'")
        return DelayAction(seconds=seconds)

    # SYR <cmd>
    if u.startswith("SYR "):
        cmd = stripped[4:].strip()
        if not cmd:
            raise ValidationError(f"SYR command is empty: '{line.strip()}'")
        return PeripheralAction(command=cmd, timeout_s=peripheral_timeout(cmd.upper()))

    if u == "SYR":
        raise ValidationError(f"SYR command is empty: '{line.strip()}'")

    # Peripheral commands
    if u.startswith(("CH", "INIT", "DEOXIDIZE", "SOLENOID", "FLUSH", "CUT", "FAN", "STATUS")):
        return PeripheralAction(command=stripped, timeout_s=peripheral_timeout(u))

    # Motion commands
    if _MOTION_RE.match(stripped):
        return MotionAction(command=stripped, wait_idle=True)

    # Motion config commands
    if u in ("G21", "G90", "G91", "G94", "G54", "M30", "$X"):
        return MotionConfigAction(command=stripped)

    if _FEED_RE.match(stripped):
        return MotionConfigAction(command=stripped)

    raise ValidationError(f"Unsupported instruction: '{line.strip()}'")


def parse_instruction_file(path: str) -> List[Action]:
    actions: List[Action] = []

    with open(path, "r", encoding="utf-8") as f:
        for idx, raw_line in enumerate(f, start=1):
            try:
                action = parse_instruction_line(raw_line)
            except ValidationError as exc:
                raise ValidationError(
                    f"{path}: line {idx}: {exc}"
                ) from exc

            if action is not None:
                actions.append(action)

    return actions