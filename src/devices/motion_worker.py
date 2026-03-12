from __future__ import annotations

from src.core.errors import DeviceProcessError, TransportError
from src.core.logging_utils import EventLogger
from src.core.models import CommandResult, DeviceHealth, DeviceName, ResultCode
from src.devices.base_worker import BaseWorker
from src.transport.legacy_adapters import LegacyMotionAdapter


class MotionWorker(BaseWorker):
    def __init__(self, adapter: LegacyMotionAdapter, logger: EventLogger) -> None:
        super().__init__(DeviceName.MOTION, logger)
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

    def execute_motion(self, cmd: str) -> CommandResult:
        self._begin_command(cmd)
        try:
            self.adapter.send_motion(cmd)
            self._set_health(DeviceHealth.HEALTHY, "motion ok")
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail="motion completed",
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

    def execute_config(self, cmd: str, wait_idle: bool = False) -> CommandResult:
        self._begin_command(cmd)
        try:
            self.adapter.send_config(cmd, wait_idle=wait_idle)
            self._set_health(DeviceHealth.HEALTHY, "config ok")
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail="config accepted",
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

    def execute_home(self) -> CommandResult:
        cmd = "$H"
        self._begin_command(cmd)
        try:
            self.adapter.home()
            self._set_health(DeviceHealth.HEALTHY, "home ok")
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail="homing completed",
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