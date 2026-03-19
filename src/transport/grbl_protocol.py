from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass(frozen=True)
class GrblFrame:
    raw: str
    kind: str
    state: Optional[str] = None


@dataclass(frozen=True)
class GrblValidation:
    ok: bool
    is_device_error: bool
    failure_class: Optional[str]
    detail: str

@dataclass(frozen=True)
class GrblExchange:
    command: str
    terminal_reply: str
    raw_lines: List[str] = field(default_factory=list)
    final_status: Optional[str] = None

def _normalize(line: str) -> str:
    return str(line).strip()


def classify_grbl_line(line: str) -> GrblFrame:
    raw = _normalize(line)

    if not raw:
        return GrblFrame(raw=raw, kind="empty")

    low = raw.lower()

    if raw.startswith("<") and raw.endswith(">"):
        return GrblFrame(raw=raw, kind="status", state=parse_status_state(raw))

    if low == "ok":
        return GrblFrame(raw=raw, kind="ok")

    if low.startswith("error:"):
        return GrblFrame(raw=raw, kind="error")

    if raw.upper().startswith("ALARM:"):
        return GrblFrame(raw=raw, kind="alarm")

    # GRBL greeting / banner after reconnect/reset
    if "GRBL" in raw.upper():
        return GrblFrame(raw=raw, kind="banner")

    return GrblFrame(raw=raw, kind="other")


def parse_status_state(status_line: str) -> Optional[str]:
    raw = _normalize(status_line)
    if not (raw.startswith("<") and raw.endswith(">")):
        return None

    inner = raw[1:-1]
    if not inner:
        return None

    first = inner.split("|", 1)[0].strip()
    return first or None


def is_status_line(line: str) -> bool:
    return classify_grbl_line(line).kind == "status"


def is_idle_status(line: str) -> bool:
    frame = classify_grbl_line(line)
    return frame.kind == "status" and (frame.state or "").upper() == "IDLE"


def is_run_status(line: str) -> bool:
    frame = classify_grbl_line(line)
    return frame.kind == "status" and (frame.state or "").upper() == "RUN"


def command_expects_idle_wait(command: str) -> bool:
    cmd = _normalize(command).upper()
    return (
        cmd.startswith("G0")
        or cmd.startswith("G1")
        or cmd.startswith("G2")
        or cmd.startswith("G3")
        or cmd == "$H"
    )


def validate_grbl_terminal_reply(command: str, line: str) -> GrblValidation:
    frame = classify_grbl_line(line)
    cmd = _normalize(command).upper()

    if frame.kind == "empty":
        return GrblValidation(
            ok=False,
            is_device_error=False,
            failure_class="PROTOCOL",
            detail=f"Empty GRBL reply for command '{command}'",
        )

    if frame.kind == "status":
        return GrblValidation(
            ok=False,
            is_device_error=False,
            failure_class="PROTOCOL",
            detail=(
                f"GRBL status frame received where terminal reply was expected. "
                f"command='{command}', reply='{line.strip()}'"
            ),
        )

    if frame.kind == "banner":
        return GrblValidation(
            ok=False,
            is_device_error=False,
            failure_class="PROTOCOL",
            detail=(
                f"Unexpected GRBL banner during active command. "
                f"command='{command}', reply='{line.strip()}'"
            ),
        )

    if frame.kind == "ok":
        return GrblValidation(
            ok=True,
            is_device_error=False,
            failure_class=None,
            detail=line.strip(),
        )

    if frame.kind in ("error", "alarm"):
        return GrblValidation(
            ok=False,
            is_device_error=True,
            failure_class="DEVICE_PROCESS",
            detail=line.strip(),
        )

    return GrblValidation(
        ok=False,
        is_device_error=False,
        failure_class="PROTOCOL",
        detail=(
            f"Unexpected GRBL reply. "
            f"command='{command}', reply='{line.strip()}'"
        ),
    )