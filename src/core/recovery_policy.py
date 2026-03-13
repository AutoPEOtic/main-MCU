from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FailureClass(str, Enum):
    TRANSPORT = "TRANSPORT"
    PROTOCOL = "PROTOCOL"
    DEVICE_PROCESS = "DEVICE_PROCESS"
    MOTION_POSE_UNCERTAIN = "MOTION_POSE_UNCERTAIN"
    OPERATOR_STOP = "OPERATOR_STOP"
    LOGIC = "LOGIC"
    UNKNOWN = "UNKNOWN"


class RecoveryAction(str, Enum):
    RETRY_STEP = "RETRY_STEP"
    RECONNECT_AND_CONTINUE = "RECONNECT_AND_CONTINUE"
    RESTART_RUN = "RESTART_RUN"
    RESTART_PROGRAM = "RESTART_PROGRAM"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"
    STOP = "STOP"


@dataclass(frozen=True)
class RecoveryDecision:
    failure_class: FailureClass
    action: RecoveryAction
    max_retries: int = 0
    clear_current_run_checkpoint: bool = False
    reconnect_motion: bool = False
    reconnect_peripheral: bool = False
    reconnect_peo: bool = False
    reconnect_spectrometer: bool = False
    require_motion_status_check: bool = False
    require_peripheral_status_check: bool = False
    require_peripheral_home_all: bool = False
    detail: str = ""