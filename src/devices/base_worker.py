from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from src.core.errors import DeviceUnhealthyError
from src.core.logging_utils import EventLogger
from src.core.models import CommandResult, DeviceHealth, DeviceName, DeviceSnapshot, ResultCode


@dataclass
class WorkerStatus:
    current_command: Optional[str] = None
    cancel_requested: bool = False


class BaseWorker:
    def __init__(self, name: DeviceName, logger: EventLogger) -> None:
        self.name = name
        self.logger = logger
        self.health = DeviceHealth.UNKNOWN
        self.detail = ""
        self._status = WorkerStatus()
        self._lock = threading.RLock()

    def open(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def reconnect(self) -> None:
        with self._lock:
            self.logger.info("worker", self.name.value, "RECONNECT", "START")
            self.close()
            self.open()
            self.healthcheck()
            self.logger.info("worker", self.name.value, "RECONNECT", "OK")

    def healthcheck(self) -> None:
        raise NotImplementedError

    def request_cancel(self) -> None:
        with self._lock:
            self._status.cancel_requested = True

    def clear_cancel(self) -> None:
        with self._lock:
            self._status.cancel_requested = False

    def _begin_command(self, command: str) -> None:
        with self._lock:
            if self.health in (DeviceHealth.UNHEALTHY, DeviceHealth.DISCONNECTED):
                raise DeviceUnhealthyError(f"{self.name.value} is not healthy: {self.health}")
            self._status.current_command = command
            self.logger.info("worker", self.name.value, command, "START")

    def _finish_command(self, result: CommandResult) -> CommandResult:
        with self._lock:
            self._status.current_command = None
            self.logger.info(
                "worker",
                self.name.value,
                result.command,
                result.code.value,
                detail=result.detail,
            )
            return result

    def _set_health(self, health: DeviceHealth, detail: str = "") -> None:
        self.health = health
        self.detail = detail

    def snapshot(self) -> DeviceSnapshot:
        return DeviceSnapshot(
            name=self.name,
            health=self.health,
            detail=self.detail,
            last_command=self._status.current_command,
            last_result=None,
        )

    def execute(self, *args, **kwargs) -> CommandResult:
        raise NotImplementedError