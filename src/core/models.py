from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class DeviceName(str, Enum):
    MOTION = "motion"
    PERIPHERAL = "peripheral"
    SPECTROMETER = "spectrometer"
    PEO = "peo"


class DeviceHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    DISCONNECTED = "DISCONNECTED"


class ResultCode(str, Enum):
    OK = "OK"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    REJECTED = "REJECTED"

class DeviceTrust(str, Enum):
    TRUSTED = "TRUSTED"
    DEGRADED = "DEGRADED"
    UNTRUSTED = "UNTRUSTED"


@dataclass(frozen=True)
class ProgramDefinition:
    name: str
    startup_instructions_path: str
    run_instructions_path: str
    Upos_values: List[float]
    PEO_time_values: List[float]
    KOH_targets: List[float]
    total_ml: float
    water_channel: str = "CH1"
    koh_stock_channel: str = "CH2"
    water_conc: float = 0.0
    koh_stock_conc: float = 1.0


@dataclass(frozen=True)
class RunContext:
    run_index: int
    total_runs: int
    program_name: str
    Upos: float
    PEO_time: float
    KOH_target: float
    total_ml: float
    mix_channels: Dict[str, float]
    mix_labels: Dict[str, float]
    required_disk_position: int


@dataclass
class CommandResult:
    device: Any
    command: str
    code: ResultCode
    detail: str = ""
    raw_lines: List[str] = field(default_factory=list)
    payload: Optional[Any] = None
    failure_class: Optional[str] = None
    resume_safe: bool = True


@dataclass
class DeviceSnapshot:
    name: DeviceName
    health: DeviceHealth
    trust: DeviceTrust
    detail: str = ""
    last_command: Optional[str] = None
    last_result: Optional[str] = None


@dataclass
class RuntimeSnapshot:
    supervisor_state: str
    program_name: Optional[str]
    run_index: int
    total_runs: int
    process: str
    params: Dict[str, Any]
    devices: Dict[str, DeviceSnapshot]
    last_event: str = ""
    error: Optional[str] = None
