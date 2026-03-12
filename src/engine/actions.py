from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


class Action:
    pass


@dataclass(frozen=True)
class DelayAction(Action):
    seconds: float


@dataclass(frozen=True)
class ReconnectAction(Action):
    target: str = "all"


@dataclass(frozen=True)
class MotionAction(Action):
    command: str
    wait_idle: bool = True


@dataclass(frozen=True)
class MotionConfigAction(Action):
    command: str


@dataclass(frozen=True)
class HomeAction(Action):
    command: str = "$H"


@dataclass(frozen=True)
class PeripheralAction(Action):
    command: str
    timeout_s: float


@dataclass(frozen=True)
class SolutionAction(Action):
    total_ml: float
    channels: Dict[str, float]
    timeout_s: float = 120.0


@dataclass(frozen=True)
class SpectrumAcquireAction(Action):
    pass


@dataclass(frozen=True)
class PEOSendValuesAction(Action):
    pass


@dataclass(frozen=True)
class PEOOnAction(Action):
    duration_s: float


@dataclass(frozen=True)
class PEOOffAction(Action):
    pass