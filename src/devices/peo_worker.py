from __future__ import annotations

from src.core.errors import DeviceProcessError, TransportError
from src.core.logging_utils import EventLogger
from src.core.models import CommandResult, DeviceHealth, DeviceName, ResultCode
from src.devices.base_worker import BaseWorker
from src.transport.legacy_adapters import LegacyPEOAdapter


class PEOWorker(BaseWorker):
    def __init__(self, adapter: LegacyPEOAdapter, logger: EventLogger) -> None:
        super().__init__(DeviceName.PEO, logger)
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

    def execute_send_values(self, upos: float) -> CommandResult:
        cmd = "SEND PEO VALUES"
        self._begin_command(cmd)
        try:
            self.adapter.send_values(upos)
            self._set_health(DeviceHealth.HEALTHY, "values sent")
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail=f"Upos={upos}",
                    payload={"Upos": upos},
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
                    payload={"Upos": upos},
                )
            )

    def execute_on(self, peo_time_s: float) -> CommandResult:
        cmd = "PEO ON"
        self._begin_command(cmd)
        try:
            self.adapter.on(peo_time_s)
            self._set_health(DeviceHealth.HEALTHY, "peo on completed")
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail=f"duration={peo_time_s}",
                    payload={"duration_s": peo_time_s},
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
                    payload={"duration_s": peo_time_s},
                )
            )

    def execute_off(self) -> CommandResult:
        cmd = "PEO OFF"
        self._begin_command(cmd)
        try:
            self.adapter.off()
            self._set_health(DeviceHealth.HEALTHY, "peo off completed")
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail="off completed",
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