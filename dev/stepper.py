import time
import serial
import serial.tools.list_ports

class stepper_communication:
    """
    GRBL (Arduino Uno) communication helper.

    Key point:
    - GRBL returns 'ok' when a command is accepted into its planner buffer,
      NOT when motion is finished.
    - To know motion is done, poll realtime status with '?' until state == Idle.
    """

    def __init__(self, description: str, baudrate: int, timeout_s: float = 1.0):
        self.description = description
        self.baudrate = baudrate
        self.timeout_s = timeout_s

        self.serial = self._open_port_by_description(description, baudrate, timeout_s)
        self._grbl_init()

    def _open_port_by_description(self, description: str, baudrate: int, timeout_s: float):
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            if p.description == description:
                ser = serial.Serial(p.device, baudrate, timeout=timeout_s)
                # Give Uno a moment (auto-reset on open is common)
                time.sleep(2.0)
                return ser
        raise RuntimeError(f"GRBL port with description '{description}' not found")

    # -------------------------
    # Low-level IO helpers
    # -------------------------
    def _write_line(self, s: str):
        self.serial.write((s.strip() + "\n").encode())

    def _readline(self) -> str:
        return self.serial.readline().decode(errors="ignore").strip()

    def _drain_input(self, max_time_s: float = 1.0):
        """Drain any pending startup chatter."""
        end = time.time() + max_time_s
        out = []
        while time.time() < end:
            line = self._readline()
            if line:
                out.append(line)
            else:
                time.sleep(0.01)
        return out

    def close(self):
        try:
            if getattr(self, "serial", None):
                self.serial.close()
        except Exception:
            pass
        self.serial = None

    def _wait_for_ok(self, timeout_s: float = 3.0):
        """
        Wait until GRBL replies 'ok' or 'error:' for the last command.
        Returns list of lines seen.
        """
        end = time.time() + timeout_s
        seen = []
        while time.time() < end:
            line = self._readline()
            if not line:
                time.sleep(0.01)
                continue
            seen.append(line)

            l = line.lower()
            if l == "ok":
                return seen
            if l.startswith("error:") or l.startswith("alarm:"):
                # Query realtime status to see which limit triggered
                try:
                    self.serial.write(b"?")
                    time.sleep(0.05)
                    status = self._readline()
                    if status:
                        print(f"[GRBL<- STATUS AFTER ALARM] {status}")
                except Exception:
                    status = "unknown"

                raise RuntimeError(
                    f"GRBL returned '{line}' (lines={seen}, status={status})"
                )

        raise TimeoutError(f"Timeout waiting for GRBL ok (lines={seen})")

    # -------------------------
    # Status parsing / waiting
    # -------------------------
    def query_status(self) -> str:
        """
        Realtime status report.
        Typical: <Idle|MPos:0.000,0.000,0.000|FS:0,0|...>
        """
        self.serial.write(b"?")  # realtime command (no newline)
        time.sleep(0.05)
        # Status usually comes as a single line, but we tolerate extra lines.
        line = self._readline()
        return line

    @staticmethod
    def _parse_state(status_line: str):
        if not status_line.startswith("<"):
            return None
        # <Idle|MPos:...> -> "Idle"
        inside = status_line[1:]
        state = inside.split("|", 1)[0]
        return state

    def wait_until_idle(self, poll_s: float = 0.10, timeout_s: float = 120.0):
        end = time.time() + timeout_s
        last = ""
        while time.time() < end:
            st = self.query_status()
            if st:
                last = st
                state = self._parse_state(st)

                if state in ("Alarm",):
                    raise RuntimeError(f"GRBL entered ALARM state: {st}")

                if state == "Idle":
                    return st

            time.sleep(poll_s)

        raise TimeoutError(f"Timeout waiting for GRBL Idle. Last status: {last}")

    # -------------------------
    # Public API
    # -------------------------
    def send_gcode(self, instruction: str, wait_idle: bool = False, ok_timeout_s: float = 3.0, idle_timeout_s: float = 120.0):
        instruction = instruction.strip()
        if not instruction:
            return

        self._write_line(instruction)
        print(f"[GRBL->] {instruction}")

        # Wait until GRBL *accepts* command
        seen = self._wait_for_ok(timeout_s=ok_timeout_s)
        for s in seen:
            print(f"[GRBL<-] {s}")

        # If it's motion (or caller asked), wait until motion complete
        if wait_idle:
            st = self.wait_until_idle(timeout_s=idle_timeout_s)
            print(f"[GRBL<-] {st}")

    def send_motion(self, instruction: str, **kwargs):
        """Convenience wrapper: always wait for Idle after sending."""
        self.send_gcode(instruction, wait_idle=True, **kwargs)

    def home(self):
        # Homing can take a long time, and some GRBL builds only reply 'ok' at the end.
        self.send_gcode("$H", wait_idle=True, ok_timeout_s=240.0, idle_timeout_s=240.0)

    def _grbl_init(self):
        # Wake up / sync
        self.serial.write(b"\r\n\r\n")
        time.sleep(0.2)
        drained = self._drain_input(1.5)
        for line in drained:
            print(f"[GRBL<-] {line}")

        # Unlock (if needed)
        try:
            self.send_gcode("$X", wait_idle=False, ok_timeout_s=3.0)
        except Exception as e:
            print(f"[GRBL] Unlock warning: {e}")

        # Optional: quick status sanity check
        st = self.query_status()
        if st:
            print(f"[GRBL<-] {st}")