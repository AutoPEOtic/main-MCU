from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PeripheralExchange:
    command: str
    reply: str
    raw_lines: List[str] = field(default_factory=list)


@dataclass
class ReplyValidation:
    ok: bool
    is_device_error: bool
    failure_class: Optional[str]
    detail: str


def _normalize(value: str) -> str:
    return " ".join(str(value).strip().split()).upper()


def _expected_success_prefixes(command: str) -> List[str]:
    cmd = _normalize(command)
    parts = cmd.split()
    if not parts:
        return []

    if cmd == "INIT":
        return ["OK INIT"]

    if cmd == "STATUS":
        return ["OK STATUS"]

    if cmd == "HOME ALL":
        return ["OK HOME ALL"]

    if cmd == "DEOXIDIZE ALL":
        return ["OK DEOXIDIZE ALL"]

    if cmd == "SOLUTION":
        return ["OK SOLUTION"]

    if parts[0] == "SOLUTION":
        return ["OK SOLUTION"]

    if parts[0] == "FLUSH" and len(parts) == 2 and parts[1] == "ALL":
        return ["OK FLUSH ALL"]

    if parts[0] == "FLUSH":
        return ["OK FLUSH"]

    if parts[0] == "SOLENOID" and len(parts) == 2:
        return [f"OK SOLENOID {parts[1]}"]

    if parts[0] == "CUT":
        return ["OK CUT"]

    if parts[0] == "FAN":
        return ["OK FAN"]

    if parts[0].startswith("CH") and len(parts) >= 2:
        ch = parts[0]
        verb = parts[1]
        if verb == "HOME":
            return [f"OK {ch} HOME"]
        if verb == "STATUS":
            return [f"OK {ch} STATUS"]
        if verb == "DEOXIDIZE":
            return [f"OK {ch} DEOXIDIZE"]
        if verb == "FLUSH":
            return [f"OK {ch} FLUSH"]
        if verb in ("ASP", "DISP", "DISP_SOL", "INIT"):
            return [f"OK {ch} {verb}"]

    return []


def validate_peripheral_reply(command: str, reply: str) -> ReplyValidation:
    cmd = _normalize(command)
    rep = _normalize(reply)

    if not rep:
        return ReplyValidation(
            ok=False,
            is_device_error=False,
            failure_class="PROTOCOL",
            detail=f"Empty peripheral reply for command '{command}'",
        )

    # Any explicit device ERR is a failure, but not a false success.
    if rep.startswith("ERR "):
        return ReplyValidation(
            ok=False,
            is_device_error=True,
            failure_class="DEVICE_PROCESS",
            detail=reply.strip(),
        )

    prefixes = _expected_success_prefixes(cmd)
    for prefix in prefixes:
        if rep.startswith(prefix):
            return ReplyValidation(
                ok=True,
                is_device_error=False,
                failure_class=None,
                detail=reply.strip(),
            )

    return ReplyValidation(
        ok=False,
        is_device_error=False,
        failure_class="PROTOCOL",
        detail=(
            f"Peripheral reply does not match command. "
            f"command='{command}', reply='{reply.strip()}'"
        ),
    )