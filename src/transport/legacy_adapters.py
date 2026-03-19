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
from src.transport.grbl_protocol import (
    GrblExchange,
    classify_grbl_line,
    command_expects_idle_wait,
    is_idle_status,
    validate_grbl_terminal_reply,
)

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

            ser = self._serial()
            try:
                ser.reset_input_buffer()
                ser.reset_output_buffer()
            except Exception:
                pass

        except Exception as exc:
            raise TransportError(f"Failed to open motion device: {exc}") from exc

    def close(self) -> None:
        try:
            ser = self._serial(optional=True)
            if ser is not None:
                ser.close()
        except Exception:
            pass
        self.dev = None

    def unlock(self) -> GrblExchange:
        return self._send_validated("$X", wait_for_idle=False)

    def healthcheck(self) -> str:
        ser = self._serial()
        try:
            status = self._poll_status_once(ser, timeout_s=2.0)
            if status is not None:
                return status

            exchange = self._send_validated("$X", wait_for_idle=False)
            return exchange.terminal_reply
        except Exception as exc:
            raise DeviceProcessError(f"Motion healthcheck failed: {exc}") from exc

    def send_motion(self, cmd: str) -> GrblExchange:
        return self._send_validated(cmd, wait_for_idle=True)

    def send_config(self, cmd: str, wait_idle: bool = False) -> GrblExchange:
        return self._send_validated(cmd, wait_for_idle=wait_idle)

    def home(self) -> GrblExchange:
        ser = self._serial()

        self._flush_input_buffer(ser)
        self._write_line(ser, "$H")

        raw_lines: list[str] = []

        final_status = self._wait_for_idle(
            ser=ser,
            timeout_s=180.0,
            raw_lines=raw_lines,
        )

        terminal_reply = self._drain_optional_ok_after_home(
            ser=ser,
            raw_lines=raw_lines,
            timeout_s=2.0,
        )

        return GrblExchange(
            command="$H",
            terminal_reply=terminal_reply or "ok",
            raw_lines=raw_lines,
            final_status=final_status,
        )

    def _send_validated(
        self,
        cmd: str,
        wait_for_idle: bool,
        reply_timeout_s: float = 5.0,
    ) -> GrblExchange:
        
        ser = self._serial()

        self._flush_input_buffer(ser)
        self._write_line(ser, cmd)

        raw_lines: list[str] = []
        terminal_reply = self._read_terminal_reply(
            ser=ser,
            cmd=cmd,
            timeout_s=reply_timeout_s,
            raw_lines=raw_lines,
        )

        validation = validate_grbl_terminal_reply(cmd, terminal_reply)
        if validation.ok is False:
            if validation.is_device_error:
                raise DeviceProcessError(validation.detail)
            raise ProtocolError(validation.detail)

        final_status: Optional[str] = None
        if wait_for_idle or command_expects_idle_wait(cmd):
            final_status = self._wait_for_idle(
                ser=ser,
                timeout_s=180.0,
                raw_lines=raw_lines,
            )

        return GrblExchange(
            command=cmd,
            terminal_reply=terminal_reply,
            raw_lines=raw_lines,
            final_status=final_status,
        )

    def _serial(self, optional: bool = False):
        ser = getattr(self.dev, "serial", None) if self.dev is not None else None
        if ser is None and not optional:
            raise TransportError("Motion device is not open")
        return ser

    def _flush_input_buffer(self, ser) -> None:
        try:
            if hasattr(ser, "reset_input_buffer"):
                ser.reset_input_buffer()
                return
        except Exception:
            pass

        try:
            while getattr(ser, "in_waiting", 0):
                ser.readline()
        except Exception:
            pass

    def _write_line(self, ser, cmd: str) -> None:
        try:
            ser.write((cmd.strip() + "\n").encode("utf-8"))
            if hasattr(ser, "flush"):
                ser.flush()
        except Exception as exc:
            raise TransportError(f"GRBL write failed [{cmd}]: {exc}") from exc

    def _read_terminal_reply(self, ser, cmd: str, timeout_s: float, raw_lines: list[str]) -> str:
        deadline = time.time() + timeout_s

        while time.time() < deadline:
            line = self._read_line_once(ser)
            if line is None:
                time.sleep(0.02)
                continue

            raw_lines.append(line)
            frame = classify_grbl_line(line)

            # Ignore async status chatter during the terminal-reply window.
            if frame.kind in ("status", "empty"):
                continue

            # banner after reset/reconnect is not success for active command
            if frame.kind == "banner":
                raise ProtocolError(
                    f"Unexpected GRBL banner during command '{cmd}': {line}"
                )

            # ok / error / alarm / weird other line
            return line

        raise TransportError(f"GRBL timeout waiting for terminal reply [{cmd}]")

    def _poll_status_once(self, ser, timeout_s: float = 2.0) -> Optional[str]:
        try:
            self._write_line(ser, "?")
        except Exception as exc:
            raise TransportError(f"GRBL status query failed: {exc}") from exc

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            line = self._read_line_once(ser)
            if line is None:
                time.sleep(0.02)
                continue

            frame = classify_grbl_line(line)
            if frame.kind == "status":
                return line

            if frame.kind in ("error", "alarm"):
                raise DeviceProcessError(f"GRBL status query failed: {line}")

            if frame.kind == "banner":
                raise ProtocolError(f"Unexpected GRBL banner during status query: {line}")

            # ignore "ok" and unrelated junk here

        raise TransportError("GRBL timeout waiting for status reply")

    def _wait_for_idle(self, ser, timeout_s: float, raw_lines: list[str]) -> str:
        deadline = time.time() + timeout_s

        while time.time() < deadline:
            try:
                self._write_line(ser, "?")
            except Exception as exc:
                raise TransportError(f"GRBL idle polling failed: {exc}") from exc

            poll_deadline = time.time() + 2.0
            saw_status_this_poll = False

            while time.time() < poll_deadline:
                line = self._read_line_once(ser)
                if line is None:
                    time.sleep(0.02)
                    continue

                raw_lines.append(line)
                frame = classify_grbl_line(line)

                if frame.kind == "status":
                    saw_status_this_poll = True
                    if is_idle_status(line):
                        return line
                    # still running / homing / alarm-like state inside status
                    continue

                if frame.kind in ("error", "alarm"):
                    raise DeviceProcessError(f"GRBL motion failed while waiting for idle: {line}")

                if frame.kind == "banner":
                    raise ProtocolError(f"Unexpected GRBL banner while waiting for idle: {line}")

                # ignore stray ok/other lines while waiting for status

            # no status seen in this poll window -> keep polling until timeout
            time.sleep(0.05)

        raise TransportError("GRBL timeout waiting for Idle state")

    def _drain_optional_ok_after_home(self, ser, raw_lines: list[str], timeout_s: float = 2.0) -> Optional[str]:
        deadline = time.time() + timeout_s

        while time.time() < deadline:
            line = self._read_line_once(ser)
            if line is None:
                time.sleep(0.02)
                continue

            raw_lines.append(line)
            frame = classify_grbl_line(line)

            if frame.kind == "ok":
                return line

            if frame.kind in ("error", "alarm"):
                raise DeviceProcessError(f"GRBL homing failed after idle: {line}")

            if frame.kind == "banner":
                raise ProtocolError(f"Unexpected GRBL banner after homing: {line}")

            # ignore extra status / other junk after homing
            if frame.kind in ("status", "other", "empty"):
                continue

        return None
    
    def _read_line_once(self, ser) -> Optional[str]:
        try:
            raw = ser.readline()
        except Exception as exc:
            raise TransportError(f"GRBL read failed: {exc}") from exc

        if raw is None:
            return None

        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace").strip()
        else:
            text = str(raw).strip()

        return text or None


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