import time
import serial
import serial.tools.list_ports
import os


class peripheral_communication:
    """
    Driver for the peripheral Pico (mixing system).

    Protocol (line-based ASCII):
      - Send one command per line (newline-terminated)
      - Pico replies with a single line starting with:
          OK ...
          ERR ...
      - Non-protocol debug lines may appear; we ignore them until OK/ERR or timeout.

    Supported command set (aligned to mode_serial_control_cchat.py):
      INIT
      HOME ALL | CHx HOME
      STATUS | CHx STATUS
      CHx ASP <ml> | CHx DISP <ml>
      DEOXIDIZE ALL | CHx DEOXIDIZE
      CHx DISP_SOL <ml>
      SOLUTION <total_ml> CH1 <r1> CH2 <r2> ...   (sum ratios == 1)
      FLUSH ALL | CHx FLUSH | FLUSH <seconds>
      SOLENOID ON|OFF
      CUT [reps]
      FAN ON|OFF|<seconds>
    """

    def __init__(self, port: str, baudrate: int, timeout_s: float = 1.0):
        self.port = port                  
        self.baudrate = baudrate
        self.timeout_s = timeout_s
        self.serial = self._open_port()
        self.sync(timeout_s=10.0)

        # Give MCU time to boot and print READY/INIT
        time.sleep(0.5)

    def _open_port(self):
        t0 = time.time()
        while time.time() - t0 < 30.0:
            if os.path.exists(self.port):
                break
            time.sleep(0.25)
        else:
            raise FileNotFoundError(f"Serial port not found after timeout: {self.port}")

        last_exc = None
        for _ in range(10):
            try:
                ser = serial.Serial(
                    self.port,
                    self.baudrate,
                    timeout=self.timeout_s,
                    write_timeout=self.timeout_s,
                )
                try:
                    ser.dtr = False
                    ser.rts = False
                except Exception:
                    pass

                time.sleep(0.2)
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                return ser
            except Exception as e:
                last_exc = e
                time.sleep(0.4)

        raise last_exc

    def close(self):
        try:
            if getattr(self, "serial", None):
                self.serial.close()
        except Exception:
            pass
        self.serial = None
    
    def sync(self, timeout_s: float = 10.0) -> None:
        """
        Active handshake: confirm the peripheral command loop is alive by
        obtaining an OK reply to a known command.

        This is robust even if we missed the one-time 'OK READY' banner.
        """
        # Drain any existing chatter quickly
        t0 = time.time()
        while time.time() - t0 < 0.5:
            raw = self.serial.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if line:
                print(f"[PERIPHERAL<-] {line}")

        deadline = time.time() + timeout_s
        last_lines = []

        while time.time() < deadline:
            # INIT is cheap and always responds when loop is running
            self.serial.write(b"INIT\n")
            print("[PERIPHERAL->] INIT")

            # Wait a short window for any reply
            t1 = time.time()
            while time.time() - t1 < 1.0:
                raw = self.serial.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                print(f"[PERIPHERAL<-] {line}")
                last_lines.append(line)
                last_lines = last_lines[-8:]

                if line.startswith("OK"):
                    return
                if line.startswith("ERR"):
                    raise RuntimeError(line)

            time.sleep(0.2)

        raise RuntimeError("Peripheral handshake failed (no OK/ERR to INIT). Last lines: " + " | ".join(last_lines))

    def send_command(self, cmd: str, expect_reply: bool = True, reply_timeout_s: float = 30.0):
        """
        Send one command line and optionally wait for an OK/ERR reply line.
        Returns:
            - reply line string (starts with OK/ERR) or None if expect_reply=False
        Raises:
            RuntimeError on ERR or timeout
        """
        cmd = cmd.strip()
        if not cmd:
            return None

        # Write command
        self.serial.write((cmd + "\n").encode("utf-8"))
        print(f"[PERIPHERAL->] {cmd}")

        if not expect_reply:
            return None

        # Read lines until OK/ERR or timeout
        t0 = time.time()
        while time.time() - t0 < reply_timeout_s:
            raw = self.serial.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            print(f"[PERIPHERAL<-] {line}")

            if line.startswith("OK"):
                return line
            if line.startswith("ERR"):
                raise RuntimeError(line)

            # Otherwise it's a non-protocol line (debug); keep reading

        raise RuntimeError(f"Peripheral reply timeout for cmd: {cmd}")

    # ---- Compatibility alias (your Linux code sometimes calls send_instruction) ----
    def send_instruction(self, cmd: str, expect_reply: bool = True, reply_timeout_s: float = 30.0):
        return self.send_command(cmd, expect_reply=expect_reply, reply_timeout_s=reply_timeout_s)

    # ---- Convenience wrappers matching the Pico command set ----

    def init(self) -> str:
        return self.send_command("INIT")

    def home_all(self) -> str:
        return self.send_command("HOME ALL")

    def home(self, ch: str) -> str:
        ch = ch.upper()
        return self.send_command(f"{ch} HOME")

    def status_all(self) -> str:
        return self.send_command("STATUS")

    def status(self, ch: str) -> str:
        ch = ch.upper()
        return self.send_command(f"{ch} STATUS")

    def aspirate(self, ch: str, ml: float) -> str:
        ch = ch.upper()
        return self.send_command(f"{ch} ASP {ml}")

    def dispense(self, ch: str, ml: float) -> str:
        ch = ch.upper()
        return self.send_command(f"{ch} DISP {ml}")

    def deoxidize_all(self) -> str:
        return self.send_command("DEOXIDIZE ALL")

    def deoxidize(self, ch: str) -> str:
        ch = ch.upper()
        return self.send_command(f"{ch} DEOXIDIZE")

    def dispense_solution(self, ch: str, ml: float) -> str:
        ch = ch.upper()
        return self.send_command(f"{ch} DISP_SOL {ml}")

    def solution(self, total_ml: float, ratios: dict[str, float]) -> str:
        """
        Build:
          SOLUTION <total_ml> CH1 <r1> CH2 <r2> ...
        ratios: {"CH1":0.3,"CH2":0.7} ; sum should be 1.0 (Pico enforces it).
        """
        parts = ["SOLUTION", str(total_ml)]
        for ch, r in ratios.items():
            parts.append(ch.upper())
            parts.append(str(r))
        return self.send_command(" ".join(parts))

    def flush(self, time: float) -> str:
        return self.send_command(f"FLUSH {time}")

    def flush_channel(self, ch: str) -> str:
        ch = ch.upper()
        return self.send_command(f"{ch} FLUSH")

    def flush_pump(self, seconds: float) -> str:
        return self.send_command(f"FLUSH {seconds}")

    def solenoid_on(self) -> str:
        return self.send_command("SOLENOID ON")

    def solenoid_off(self) -> str:
        return self.send_command("SOLENOID OFF")

    def cut(self, reps: int | None = None) -> str:
        if reps is None:
            return self.send_command("CUT")
        return self.send_command(f"CUT {int(reps)}")

    def fan_on(self) -> str:
        return self.send_command("FAN ON")

    def fan_off(self) -> str:
        return self.send_command("FAN OFF")

    def fan_for(self, seconds: float) -> str:
        return self.send_command(f"FAN {seconds}")
