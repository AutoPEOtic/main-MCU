import time
import serial
import serial.tools.list_ports


class PeripheralMCU:
    """
    Driver for the peripheral Pico (mixing system).
    Communicates using line-based ASCII protocol:
    - Commands: CH1 DISP 5, SOLUTION 18 A 0.3 B 0.6 C 0.1, SOLENOID ON, FLUSH 5, ...
    - Responses: OK ... / ERR ...
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
            line = self.serial.readline()
            if not line:
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

    # Optional convenience wrappers (useful later)
    def init(self):
        return self.send_command("INIT")

    def home_all(self):
        return self.send_command("HOME ALL")

    def deoxidize_all(self):
        return self.send_command("DEOXIDIZE ALL")

    def flush(self, seconds: float):
        return self.send_command(f"FLUSH {seconds}")

    def solenoid_on(self):
        return self.send_command("SOLENOID ON")

    def solenoid_off(self):
        return self.send_command("SOLENOID OFF")
