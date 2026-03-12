from __future__ import annotations

from src.core.errors import DeviceProcessError, TransportError
from src.core.logging_utils import EventLogger
from src.core.models import CommandResult, DeviceHealth, DeviceName, ResultCode
from src.devices.base_worker import BaseWorker
from src.transport.legacy_adapters import LegacyPeripheralAdapter


class PeripheralWorker(BaseWorker):
    def __init__(self, adapter: LegacyPeripheralAdapter, logger: EventLogger) -> None:
        super().__init__(DeviceName.PERIPHERAL, logger)
        self.adapter = adapter

    def open(self) -> None:
        try:
            self.adapter.open()
            self._set_health(DeviceHealth.HEALTHY, "opened")
        except Exception as exc:
            self._set_health(DeviceHealth.DISCONNECTED, str(exc))
            raise

    def close(self) -> None:
        self.adapter.close()
        self._set_health(DeviceHealth.DISCONNECTED, "closed")

    def healthcheck(self) -> None:
        try:
            self.adapter.healthcheck()
            self._set_health(DeviceHealth.HEALTHY, "healthcheck ok")
        except Exception as exc:
            self._set_health(DeviceHealth.UNHEALTHY, str(exc))
            raise

    def execute_text(self, cmd: str, timeout_s: float) -> CommandResult:
        self._begin_command(cmd)
        try:
            reply = self.adapter.send_text(cmd, timeout_s=timeout_s)
            self._set_health(DeviceHealth.HEALTHY, "last command ok")
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail=str(reply),
                    raw_lines=[str(reply)] if reply else [],
                )
            )
        except (TransportError, DeviceProcessError) as exc:
            self._set_health(DeviceHealth.UNHEALTHY, str(exc))
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.ERROR,
                    detail=str(exc),
                )
            )

    def execute_solution(self, total_ml: float, channels: dict[str, float], timeout_s: float) -> CommandResult:
        cmd = f"SOLUTION total_ml={total_ml}"
        self._begin_command(cmd)
        try:
            reply = self.adapter.solution(total_ml=total_ml, channels=channels, timeout_s=timeout_s)
            self._set_health(DeviceHealth.HEALTHY, "solution ok")
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail=str(reply),
                    raw_lines=[str(reply)] if reply else [],
                    payload={"total_ml": total_ml, "channels": channels},
                )
            )
        except (TransportError, DeviceProcessError) as exc:
            self._set_health(DeviceHealth.UNHEALTHY, str(exc))
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.ERROR,
                    detail=str(exc),
                    payload={"total_ml": total_ml, "channels": channels},
                )
            )