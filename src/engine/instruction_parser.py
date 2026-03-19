from __future__ import annotations

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


def peripheral_timeout(command_upper: str) -> float:
    for prefix, timeout_s in _PERIPHERAL_TIMEOUTS.items():
        if command_upper.startswith(prefix):
            return timeout_s
    if command_upper.startswith("CH"):
        return 60.0
    return 30.0


def parse_instruction_line(line: str) -> Action | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    u = stripped.upper()

    if u.startswith("LINE ONE"):
        return None

    if u.startswith("RECONNECT"):
        return ReconnectAction(target="all")

    if u.startswith("PAUSE"):
        instruction_clean = stripped.split(";")[0].strip()
        parts = instruction_clean.split()
        if len(parts) != 2:
            raise ValidationError(f"Invalid PAUSE instruction: {line}")
        try:
            seconds = float(parts[1]) / 10.0
        except ValueError as exc:
            raise ValidationError(f"Invalid PAUSE value: {line}") from exc
        return DelayAction(seconds=seconds)

    if u.startswith("HOME"):
        return HomeAction()

    if u.startswith("SPECTRUM GET"):
        return SpectrumAcquireAction()

    if u.startswith("SEND PEO VALUES"):
        return PEOSendValuesAction()

    if u.startswith("PEO ON"):
        return PEOOnAction(duration_s=-1.0)  # resolved later from run context

    if u.startswith("PEO OFF"):
        return PEOOffAction()

    if u.startswith(("CH", "INIT", "DEOXIDIZE", "SOLENOID", "FLUSH", "CUT", "FAN", "STATUS")):
        return PeripheralAction(command=stripped, timeout_s=peripheral_timeout(u))
    
    if u.startswith(("G0", "G1", "G2", "G3")):
        return MotionAction(command=stripped, wait_idle=True)

    if u.startswith(("G21", "G90", "G91", "G94", "G54", "M30", "F", "$X")):
        return MotionConfigAction(command=stripped)

    if u.startswith("SOLUTION"):
        # Placeholder action. Actual channels are injected from run context later.
        return SolutionAction(total_ml=-1.0, channels={})

    if u.startswith("SYR "):
        cmd = stripped[4:].strip()
        if not cmd:
            raise ValidationError("SYR command is empty")
        return PeripheralAction(command=cmd, timeout_s=peripheral_timeout(cmd.upper()))

    raise ValidationError(f"Unsupported instruction: {line}")


def parse_instruction_file(path: str) -> List[Action]:
    actions: List[Action] = []
    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            action = parse_instruction_line(line)
            if action is not None:
                actions.append(action)
    return actions