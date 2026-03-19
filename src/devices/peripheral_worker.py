from __future__ import annotations

from src.core.errors import DeviceProcessError, ProtocolError, TransportError
from src.core.logging_utils import EventLogger
from src.core.models import CommandResult, DeviceHealth, DeviceName, DeviceTrust, ResultCode
from src.core.recovery_policy import FailureClass
from src.devices.base_worker import BaseWorker
from src.transport.legacy_adapters import LegacyPeripheralAdapter


class PeripheralWorker(BaseWorker):
    def __init__(self, adapter: LegacyPeripheralAdapter, logger: EventLogger) -> None:
        super().__init__(DeviceName.PERIPHERAL, logger)
        self.adapter = adapter

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

    def open(self) -> None:
        try:
            self.adapter.open()
            self._set_health(DeviceHealth.HEALTHY, "opened")
            self._set_trust(DeviceTrust.TRUSTED)
        except Exception as exc:
            self._set_health(DeviceHealth.DISCONNECTED, str(exc))
            self._set_trust(DeviceTrust.UNTRUSTED)
            raise

    def close(self) -> None:
        self.adapter.close()
        self._set_health(DeviceHealth.DISCONNECTED, "closed")
        self._set_trust(DeviceTrust.UNTRUSTED)

    def healthcheck(self) -> None:
        try:
            self.adapter.healthcheck()
            self._set_health(DeviceHealth.HEALTHY, "healthcheck ok")
            self._set_trust(DeviceTrust.TRUSTED)
        except Exception as exc:
            self._set_health(DeviceHealth.UNHEALTHY, str(exc))
            self._set_trust(DeviceTrust.UNTRUSTED)
            raise

    def execute_text(self, cmd: str, timeout_s: float) -> CommandResult:
        self._begin_command(cmd)
        try:
            exchange = self.adapter.send_text(cmd, timeout_s=timeout_s)
            self._set_health(DeviceHealth.HEALTHY, "last command ok")
            self._set_trust(DeviceTrust.TRUSTED)
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail=exchange.reply,
                    raw_lines=list(exchange.raw_lines),
                    failure_class=None,
                    resume_safe=True,
                )
            )

        except ProtocolError as exc:
            detail = str(exc)
            self._set_health(DeviceHealth.UNHEALTHY, detail)
            self._set_trust(DeviceTrust.UNTRUSTED)
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.ERROR,
                    detail=detail,
                    raw_lines=[detail],
                    failure_class=FailureClass.PROTOCOL.value,
                    resume_safe=False,
                )
            )

        except (TransportError, DeviceProcessError) as exc:
            detail = str(exc)
            upper = cmd.upper()

            if upper.startswith("HOME ALL") and self._is_bad_homing(detail):
                self._set_health(DeviceHealth.DEGRADED, detail)
                self._set_trust(DeviceTrust.DEGRADED)
                return self._finish_command(
                    CommandResult(
                        device=self.name,
                        command=cmd,
                        code=ResultCode.ERROR,
                        detail=detail,
                        raw_lines=[detail],
                        failure_class=FailureClass.DEVICE_PROCESS.value,
                        resume_safe=False,
                    )
                )

            if self._is_transport_like(detail):
                self._set_health(DeviceHealth.UNHEALTHY, detail)
                self._set_trust(DeviceTrust.UNTRUSTED)
                return self._finish_command(
                    CommandResult(
                        device=self.name,
                        command=cmd,
                        code=ResultCode.ERROR,
                        detail=detail,
                        raw_lines=[detail],
                        failure_class=FailureClass.TRANSPORT.value,
                        resume_safe=False,
                    )
                )

            self._set_health(DeviceHealth.DEGRADED, detail)
            self._set_trust(DeviceTrust.DEGRADED)
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.ERROR,
                    detail=detail,
                    raw_lines=[detail],
                    failure_class=FailureClass.DEVICE_PROCESS.value,
                    resume_safe=False,
                )
            )

    def execute_solution(self, total_ml: float, channels: dict[str, float], timeout_s: float) -> CommandResult:
        cmd = f"SOLUTION total_ml={total_ml}"
        self._begin_command(cmd)
        try:
            exchange = self.adapter.solution(total_ml=total_ml, channels=channels, timeout_s=timeout_s)
            self._set_health(DeviceHealth.HEALTHY, "solution ok")
            self._set_trust(DeviceTrust.TRUSTED)
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail=exchange.reply,
                    raw_lines=list(exchange.raw_lines),
                    payload={"total_ml": total_ml, "channels": channels},
                    failure_class=None,
                    resume_safe=True,
                )
            )

        except ProtocolError as exc:
            detail = str(exc)
            self._set_health(DeviceHealth.UNHEALTHY, detail)
            self._set_trust(DeviceTrust.UNTRUSTED)
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.ERROR,
                    detail=detail,
                    raw_lines=[detail],
                    payload={"total_ml": total_ml, "channels": channels},
                    failure_class=FailureClass.PROTOCOL.value,
                    resume_safe=False,
                )
            )

        except (TransportError, DeviceProcessError) as exc:
            detail = str(exc)

            if self._is_transport_like(detail):
                self._set_health(DeviceHealth.UNHEALTHY, detail)
                self._set_trust(DeviceTrust.UNTRUSTED)
                return self._finish_command(
                    CommandResult(
                        device=self.name,
                        command=cmd,
                        code=ResultCode.ERROR,
                        detail=detail,
                        raw_lines=[detail],
                        payload={"total_ml": total_ml, "channels": channels},
                        failure_class=FailureClass.TRANSPORT.value,
                        resume_safe=False,
                    )
                )

            self._set_health(DeviceHealth.DEGRADED, detail)
            self._set_trust(DeviceTrust.DEGRADED)
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.ERROR,
                    detail=detail,
                    raw_lines=[detail],
                    payload={"total_ml": total_ml, "channels": channels},
                    failure_class=FailureClass.DEVICE_PROCESS.value,
                    resume_safe=False,
                )
            )