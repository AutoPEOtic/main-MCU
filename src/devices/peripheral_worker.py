from __future__ import annotations

from src.core.errors import DeviceProcessError, TransportError
from src.core.logging_utils import EventLogger
from src.core.models import CommandResult, DeviceHealth, DeviceName, ResultCode
from src.devices.base_worker import BaseWorker
from src.transport.legacy_adapters import LegacyPeripheralAdapter
from src.core.recovery_policy import FailureClass
from src.core.models import DeviceTrust


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
            self._set_trust(DeviceTrust.TRUSTED)
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail=str(reply),
                    raw_lines=[str(reply)] if reply else [],
                    failure_class=None,
                    resume_safe=True,
                )
            )
        except (TransportError, DeviceProcessError) as exc:
            detail = str(exc)
            upper = cmd.upper()

            # Special case: HOME ALL bad homing is recoverable and should be retryable.
            if upper.startswith("HOME ALL") and self._is_bad_homing(detail):
                self._set_health(DeviceHealth.DEGRADED, detail)
                self._set_trust(DeviceTrust.DEGRADED)
                return self._finish_command(
                    CommandResult(
                        device=self.name,
                        command=cmd,
                        code=ResultCode.ERROR,
                        detail=detail,
                        failure_class=FailureClass.DEVICE_PROCESS.value,
                        resume_safe=False,
                    )
                )

            # Transport / serial-like failure -> block further commands until recovery
            if self._is_transport_like(detail):
                self._set_health(DeviceHealth.UNHEALTHY, detail)
                self._set_trust(DeviceTrust.UNTRUSTED)
                return self._finish_command(
                    CommandResult(
                        device=self.name,
                        command=cmd,
                        code=ResultCode.ERROR,
                        detail=detail,
                        failure_class=FailureClass.TRANSPORT.value,
                        resume_safe=False,
                    )
                )

            # Generic device-process failure
            self._set_health(DeviceHealth.DEGRADED, detail)
            self._set_trust(DeviceTrust.DEGRADED)
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.ERROR,
                    detail=detail,
                    failure_class=FailureClass.DEVICE_PROCESS.value,
                    resume_safe=False,
                )
            )
        

    def execute_solution(self, total_ml: float, channels: dict[str, float], timeout_s: float) -> CommandResult:
        cmd = f"SOLUTION total_ml={total_ml}"
        self._begin_command(cmd)
        try:
            reply = self.adapter.solution(total_ml=total_ml, channels=channels, timeout_s=timeout_s)
            self._set_health(DeviceHealth.HEALTHY, "solution ok")
            self._set_trust(DeviceTrust.TRUSTED)
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail=str(reply),
                    raw_lines=[str(reply)] if reply else [],
                    payload={"total_ml": total_ml, "channels": channels},
                    failure_class=None,
                    resume_safe=True,
                )
            )
        except (TransportError, DeviceProcessError) as exc:
            detail = str(exc)

            if self._is_transport_like(detail):
                self._set_health(DeviceHealth.UNHEALTHY, detail)
                self._set_trust(DeviceTrust.UNTRUSTED)
                failure_class = FailureClass.TRANSPORT.value
            else:
                self._set_health(DeviceHealth.DEGRADED, detail)
                self._set_trust(DeviceTrust.DEGRADED)
                failure_class = FailureClass.DEVICE_PROCESS.value

            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.ERROR,
                    detail=detail,
                    payload={"total_ml": total_ml, "channels": channels},
                    failure_class=failure_class,
                    resume_safe=False,
                )
            )
    @staticmethod
    def _is_bad_homing(detail: str) -> bool:
        d = detail.lower()
        return (
            "limit signal not stable during homing" in d
            or "bad homing" in d
            or ("hom" in d and "limit" in d)
        )

    @staticmethod
    def _is_transport_like(detail: str) -> bool:
        d = detail.lower()
        return (
            "write failed" in d
            or "input/output error" in d
            or "timed out" in d
            or "timeout" in d
            or "not open" in d
            or "serial" in d
        )
