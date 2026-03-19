from __future__ import annotations

import time
import subprocess
from typing import Any, Optional

import settings.config as legacy_config

from dev.peripherals import peripheral_communication
from dev.stepper import stepper_communication
from dev.spectrometer import spectrometer_communication
from dev.peo import peo_communication

from src.config.runtime_config import RuntimeConfig
from src.core.errors import TransportError, DeviceProcessError, ProtocolError
from src.transport.peripheral_protocol import PeripheralExchange, validate_peripheral_reply


class LegacyPeripheralAdapter:
    def __init__(self, cfg: RuntimeConfig) -> None:
        self.cfg = cfg
        self.dev: Optional[peripheral_communication] = None

    def open(self) -> None:
        try:
            self.dev = peripheral_communication(
                port=self.cfg.peripheral_port,
                baudrate=self.cfg.peripheral_baudrate,
                timeout_s=1.0,
            )
            # Active sync / healthcheck
            self._send_validated("STATUS", reply_timeout_s=5.0)
        except Exception as exc:
            raise TransportError(f"Failed to open peripheral device: {exc}") from exc

    def close(self) -> None:
        try:
            if self.dev is not None:
                self.dev.close()
        except Exception:
            pass
        self.dev = None

    def healthcheck(self) -> str:
        if self.dev is None:
            raise TransportError("Peripheral device is not open")
        exchange = self._send_validated("STATUS", reply_timeout_s=5.0)
        return exchange.reply

    def send_text(self, cmd: str, timeout_s: float) -> PeripheralExchange:
        if self.dev is None:
            raise TransportError("Peripheral device is not open")
        return self._send_validated(cmd, reply_timeout_s=timeout_s)

    def solution(self, total_ml: float, channels: dict[str, float], timeout_s: float) -> PeripheralExchange:
        if self.dev is None:
            raise TransportError("Peripheral device is not open")
        cmd = self._build_solution_command(total_ml, channels)
        return self._send_validated(cmd, reply_timeout_s=timeout_s)

    def _send_validated(self, cmd: str, reply_timeout_s: float) -> PeripheralExchange:
        if self.dev is None:
            raise TransportError("Peripheral device is not open")

        self._flush_input_buffer()

        try:
            reply = self.dev.send_command(cmd, reply_timeout_s=reply_timeout_s)
        except Exception as exc:
            raise TransportError(f"Peripheral transport failed [{cmd}]: {exc}") from exc

        exchange = PeripheralExchange(
            command=cmd,
            reply=str(reply).strip(),
            raw_lines=[str(reply).strip()] if reply is not None else [],
        )

        validation = validate_peripheral_reply(cmd, exchange.reply)

        if validation.ok:
            return exchange

        if validation.is_device_error:
            raise DeviceProcessError(validation.detail)

        raise ProtocolError(validation.detail)

    def _flush_input_buffer(self) -> None:
        if self.dev is None:
            return

        ser = getattr(self.dev, "serial", None)
        if ser is None:
            return

        # Best case: pyserial-style buffer reset
        try:
            if hasattr(ser, "reset_input_buffer"):
                ser.reset_input_buffer()
                return
        except Exception:
            pass

        # Fallback: drain readable lines manually
        try:
            while getattr(ser, "in_waiting", 0):
                ser.readline()
        except Exception:
            pass

    @staticmethod
    def _build_solution_command(total_ml: float, channels: dict[str, float]) -> str:
        parts = ["SOLUTION", str(total_ml)]
        for ch, ratio in channels.items():
            parts.extend([ch.upper(), str(ratio)])
        return " ".join(parts)

class LegacyMotionAdapter:
    def __init__(self, cfg: RuntimeConfig) -> None:
        self.cfg = cfg
        self.dev: Optional[stepper_communication] = None

    def open(self) -> None:
        try:
            self.dev = stepper_communication(
                self.cfg.stepper_description,
                self.cfg.stepper_baudrate,
            )

            ser = getattr(self.dev, "serial", None)
            if ser is not None:
                try:
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()
                except Exception:
                    pass

        except Exception as exc:
            raise TransportError(f"Failed to open motion device: {exc}") from exc

    def close(self) -> None:
        try:
            if self.dev is not None and getattr(self.dev, "serial", None):
                self.dev.serial.close()
        except Exception:
            pass
        self.dev = None

    def unlock(self) -> None:
        if self.dev is None:
            raise TransportError("Motion device is not open")
        try:
            self.dev.send_gcode("$X", wait_idle=False)
        except Exception as exc:
            raise DeviceProcessError(f"Motion unlock failed: {exc}") from exc

    def healthcheck(self) -> str:
        if self.dev is None:
            raise TransportError("Motion device is not open")
        try:
            # query status through existing GRBL object if available
            if hasattr(self.dev, "query_status"):
                return str(self.dev.query_status())
            # fallback: lightweight non-motion command
            self.dev.send_gcode("$X", wait_idle=False)
            return "OK"
        except Exception as exc:
            raise DeviceProcessError(f"Motion healthcheck failed: {exc}") from exc

    def send_motion(self, cmd: str) -> None:
        if self.dev is None:
            raise TransportError("Motion device is not open")
        try:
            self.dev.send_motion(cmd)
        except Exception as exc:
            raise DeviceProcessError(f"Motion command failed [{cmd}]: {exc}") from exc

    def send_config(self, cmd: str, wait_idle: bool = False) -> None:
        if self.dev is None:
            raise TransportError("Motion device is not open")
        try:
            self.dev.send_gcode(cmd, wait_idle=wait_idle)
        except Exception as exc:
            raise DeviceProcessError(f"Motion config failed [{cmd}]: {exc}") from exc

    def home(self) -> None:
        if self.dev is None:
            raise TransportError("Motion device is not open")
        try:
            self.dev.home()
        except Exception as exc:
            raise DeviceProcessError(f"Motion homing failed: {exc}") from exc


class LegacySpectrometerAdapter:
    def __init__(self, cfg: RuntimeConfig) -> None:
        self.cfg = cfg
        self.dev: Optional[spectrometer_communication] = None

    def open(self) -> None:
        try:
            self.dev = spectrometer_communication(
                self.cfg.spectrometer_description,
                self.cfg.spectrometer_baudrate,
            )
        except Exception as exc:
            raise TransportError(f"Failed to open spectrometer device: {exc}") from exc

    def close(self) -> None:
        try:
            if self.dev is not None and getattr(self.dev, "serial", None):
                self.dev.serial.close()
        except Exception:
            pass
        self.dev = None

    def healthcheck(self) -> str:
        if self.dev is None:
            raise TransportError("Spectrometer device is not open")
        try:
            # Old implementation has no dedicated health command.
            # Presence of serial object is the minimum viable check.
            if getattr(self.dev, "serial", None) is None:
                raise RuntimeError("serial is not initialized")
            return "OK"
        except Exception as exc:
            raise DeviceProcessError(f"Spectrometer healthcheck failed: {exc}") from exc

    def get_spectrum(self) -> str:
        if self.dev is None:
            raise TransportError("Spectrometer device is not open")
        try:
            return self.dev.get_spectrum()
        except Exception as exc:
            raise DeviceProcessError(f"Spectrometer acquisition failed: {exc}") from exc


class LegacyPEOAdapter:
    def __init__(self, cfg: RuntimeConfig) -> None:
        self.cfg = cfg
        self.dev: Optional[peo_communication] = None

    def open(self) -> None:
        try:
            self.dev = peo_communication(
                self.cfg.peo_description,
                self.cfg.peo_baudrate,
                self.cfg.peo_parity,
                self.cfg.peo_stopbits,
                self.cfg.peo_bytesize,
                0,  # Upos is written later dynamically
                self.cfg.peo_Ipos,
                self.cfg.peo_Uneg,
                self.cfg.peo_Ineg,
                self.cfg.peo_pulsepos,
                self.cfg.peo_pause1,
                self.cfg.peo_pulseneg,
                self.cfg.peo_pause2,
                self.cfg.peo_multiplier,
            )
        except Exception as exc:
            raise TransportError(f"Failed to open PEO device: {exc}") from exc

    def close(self) -> None:
        try:
            if self.dev is not None and getattr(self.dev, "serial", None):
                self.dev.serial.close()
        except Exception:
            pass
        self.dev = None

    def healthcheck(self) -> str:
        if self.dev is None:
            raise TransportError("PEO device is not open")
        try:
            if getattr(self.dev, "serial", None) is None:
                raise RuntimeError("modbus client is not initialized")
            return "OK"
        except Exception as exc:
            raise DeviceProcessError(f"PEO healthcheck failed: {exc}") from exc

    def send_values(self, upos: float) -> None:
        if self.dev is None:
            raise TransportError("PEO device is not open")
        try:
            self.dev.send_values(upos)
        except Exception as exc:
            raise DeviceProcessError(f"PEO send_values failed: {exc}") from exc

    def on(self, peo_time_s: float) -> None:
        if self.dev is None:
            raise TransportError("PEO device is not open")
        try:
            self.dev.on(peo_time_s)
        except Exception as exc:
            raise DeviceProcessError(f"PEO ON failed: {exc}") from exc

    def off(self) -> None:
        if self.dev is None:
            raise TransportError("PEO device is not open")
        try:
            self.dev.off()
        except Exception as exc:
            raise DeviceProcessError(f"PEO OFF failed: {exc}") from exc


def cycle_usb_hubs() -> None:
    """
    Legacy global bus reset, kept only inside the Device Manager path.
    This mirrors the current autopeotic.connect() behavior during migration.
    """
    for hub in ("1", "2", "3", "4"):
        subprocess.run(["sudo", "uhubctl", "-a", "cycle", "-l", hub], check=False)
    time.sleep(5.0)

def is_valid_reply(cmd, reply):
    cmd = cmd.upper()

    if cmd.startswith("HOME"):
        return reply.startswith("OK HOME")

    if cmd.startswith("STATUS"):
        return reply.startswith("OK STATUS")

    if cmd.startswith("CUT"):
        return reply.startswith("OK CUT")

    if cmd.startswith("SOLUTION"):
        return reply.startswith("OK SOLUTION")

    if cmd.startswith("CH"):
        parts = cmd.split()
        if len(parts) >= 2:
            return reply.startswith(f"OK {parts[0]} {parts[1]}")

    return False