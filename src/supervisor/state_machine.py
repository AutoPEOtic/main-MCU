from __future__ import annotations

from enum import Enum
from typing import Dict, Set

from src.core.errors import SupervisorStateError


class SupervisorState(str, Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    RECOVERING = "RECOVERING"
    ERROR = "ERROR"


_ALLOWED: Dict[SupervisorState, Set[SupervisorState]] = {
    SupervisorState.IDLE: {
        SupervisorState.STARTING,
        SupervisorState.RECOVERING,
    },
    SupervisorState.STARTING: {
        SupervisorState.RUNNING,
        SupervisorState.ERROR,
        SupervisorState.STOPPING,
    },
    SupervisorState.RUNNING: {
        SupervisorState.PAUSED,
        SupervisorState.STOPPING,
        SupervisorState.RECOVERING,
        SupervisorState.ERROR,
    },
    SupervisorState.PAUSED: {
        SupervisorState.RUNNING,
        SupervisorState.STOPPING,
        SupervisorState.RECOVERING,
        SupervisorState.ERROR,
    },
    SupervisorState.STOPPING: {
        SupervisorState.IDLE,
        SupervisorState.ERROR,
    },
    SupervisorState.RECOVERING: {
        SupervisorState.IDLE,
        SupervisorState.RUNNING,
        SupervisorState.ERROR,
    },
    SupervisorState.ERROR: {
        SupervisorState.IDLE,
        SupervisorState.RECOVERING,
    },
}


class StateMachine:
    def __init__(self) -> None:
        self._state = SupervisorState.IDLE

    @property
    def state(self) -> SupervisorState:
        return self._state

    def transition(self, new_state: SupervisorState) -> None:
        if new_state == self._state:
            return
        if new_state not in _ALLOWED[self._state]:
            raise SupervisorStateError(f"Illegal transition: {self._state} -> {new_state}")
        self._state = new_state