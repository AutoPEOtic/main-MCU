from __future__ import annotations

from src.core.errors import DeviceProcessError, ProtocolError, TransportError
from src.core.logging_utils import EventLogger
from src.core.models import CommandResult, DeviceHealth, DeviceName, DeviceTrust, ResultCode
from src.core.recovery_policy import FailureClass
from src.devices.base_worker import BaseWorker
from src.transport.legacy_adapters import LegacyMotionAdapter


class MotionWorker(BaseWorker):
    def __init__(self, adapter: LegacyMotionAdapter, logger: EventLogger) -> None:
        super().__init__(DeviceName.MOTION, logger)
        self.adapter = adapter

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
            or "read failed" in d
        )

    @staticmethod
    def _is_alarm_like(detail: str) -> bool:
        d = detail.lower()
        return "alarm:" in d or "grbl motion failed while waiting for idle" in d

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

    def execute_motion(self, cmd: str) -> CommandResult:
        self._begin_command(cmd)
        try:
            exchange = self.adapter.send_motion(cmd)
            self._set_health(DeviceHealth.HEALTHY, "motion ok")
            self._set_trust(DeviceTrust.TRUSTED)
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail=exchange.terminal_reply,
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

            if self._is_alarm_like(detail):
                self._set_health(DeviceHealth.DEGRADED, detail)
                self._set_trust(DeviceTrust.DEGRADED)
                return self._finish_command(
                    CommandResult(
                        device=self.name,
                        command=cmd,
                        code=ResultCode.ERROR,
                        detail=detail,
                        raw_lines=[detail],
                        failure_class=FailureClass.MOTION_POSE_UNCERTAIN.value,
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

    def execute_config(self, cmd: str, wait_idle: bool = False) -> CommandResult:
        self._begin_command(cmd)
        try:
            exchange = self.adapter.send_config(cmd, wait_idle=wait_idle)
            self._set_health(DeviceHealth.HEALTHY, "config ok")
            self._set_trust(DeviceTrust.TRUSTED)
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail=exchange.terminal_reply,
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

            if self._is_alarm_like(detail):
                self._set_health(DeviceHealth.DEGRADED, detail)
                self._set_trust(DeviceTrust.DEGRADED)
                return self._finish_command(
                    CommandResult(
                        device=self.name,
                        command=cmd,
                        code=ResultCode.ERROR,
                        detail=detail,
                        raw_lines=[detail],
                        failure_class=FailureClass.MOTION_POSE_UNCERTAIN.value,
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

    def execute_home(self) -> CommandResult:
        cmd = "$H"
        self._begin_command(cmd)
        try:
            exchange = self.adapter.home()
            self._set_health(DeviceHealth.HEALTHY, "home ok")
            self._set_trust(DeviceTrust.TRUSTED)
            return self._finish_command(
                CommandResult(
                    device=self.name,
                    command=cmd,
                    code=ResultCode.OK,
                    detail=exchange.terminal_reply,
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

            if self._is_alarm_like(detail):
                self._set_health(DeviceHealth.DEGRADED, detail)
                self._set_trust(DeviceTrust.DEGRADED)
                return self._finish_command(
                    CommandResult(
                        device=self.name,
                        command=cmd,
                        code=ResultCode.ERROR,
                        detail=detail,
                        raw_lines=[detail],
                        failure_class=FailureClass.MOTION_POSE_UNCERTAIN.value,
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