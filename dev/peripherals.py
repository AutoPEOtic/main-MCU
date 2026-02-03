import time
import serial
import serial.tools.list_ports


class PeripheralMCU:
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

    def __init__(self, description: str, baudrate: int, timeout_s: float = 1.0):
        self.description = description
        self.baudrate = baudrate
        self.timeout_s = timeout_s
        self.serial = self._open_port()

        # Give MCU time to boot and print READY/INIT
        time.sleep(0.5)
        self._drain_input()

    def _open_port(self):
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if port.description == self.description:
                return serial.Serial(port.device, self.baudrate, timeout=self.timeout_s)
        raise RuntimeError(f"Peripheral MCU not found by description: {self.description}")

    def _drain_input(self):
        """Read and discard any buffered lines (boot banners, READY, etc.)."""
        t0 = time.time()
        while time.time() - t0 < 0.3:
            raw = self.serial.readline()
            if not raw:
                break

    def send_command(self, cmd: str, expect_reply: bool = True, reply_timeout_s: float = 3.0) -> str | None:
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
    def send_instruction(self, cmd: str, expect_reply: bool = True, reply_timeout_s: float = 3.0) -> str | None:
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

    def flush_all(self) -> str:
        return self.send_command("FLUSH ALL")

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
