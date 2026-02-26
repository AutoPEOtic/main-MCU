import time
from src.database import database


class sender:
    """
    Host-side instruction dispatcher.

    This version matches the peripheral Pico's *text* protocol:
      - INIT
      - HOME ALL / CHx HOME
      - CHx ASP <ml> / CHx DISP <ml>
      - STATUS / CHx STATUS
      - DEOXIDIZE ALL / CHx DEOXIDIZE
      - DISP_SOL (note: Pico expects CHx DISP_SOL <ml>, so we support that too)
      - SOLUTION <total_ml> CH1 <r1> CH2 <r2> ...
      - FLUSH ALL / CHx FLUSH / FLUSH <seconds>
      - SOLENOID ON|OFF
      - FAN ON|OFF|<seconds>
      - CUT [reps]
      - plus your stepper G-code lines routed to stepper controller
    """

    def __init__(self, peripherals, stepper, spectrum=None, peo=None):
        self.peripherals = peripherals  # must implement send_instruction(line: str)
        self.stepper = stepper
        self.spectrum = spectrum
        self.peo = peo
        self.autopeotic_db = database()

    def _send_pico(self, line: str):
        """
        Send one *text* command line to the peripheral Pico.
        Assumes peripherals.send_instruction() handles newline + waiting for OK/ERR.
        """
        self.peripherals.send_instruction(line)

    def send_instruction(self, autopeotic, instruction: str, line_no: int):
        # IMPORTANT: strip must be assigned (old code had a bug)
        instruction = instruction.strip()

        # skip empty / comments
        if not instruction or instruction.startswith("#"):
            return

        u = instruction.upper()

        # ------------------------------
        # Local-only commands (Linux side)
        # ------------------------------
        if u.startswith("PAUSE"):
            # PAUSE <ticks> (your previous logic: /10 seconds)
            parts = instruction.split(maxsplit=1)
            if len(parts) != 2:
                print(f'ERROR instruction "{instruction}" bad PAUSE format in line {line_no}')
                return
            delay = parts[1].strip()
            try:
                time.sleep(float(delay) / 10.0)
            except Exception:
                print(f'ERROR instruction "{instruction}" bad PAUSE value in line {line_no}')
            return

        # ------------------------------
        # Stepper controller passthrough
        # ------------------------------
        if u.startswith(("G1", "G21", "G90", "G91", "M30", "F")):
            self.stepper.send_instruction(instruction)
            return

        # ------------------------------
        # Spectrum / PEO passthrough
        # ------------------------------
        if u.startswith("SPECTRUM GET"):
            self.autopeotic_db.send(self.autopeotic_db.generate_query(self.spectrum.get_spectrum()))
            autopeotic.progress = "measuring spectrum"
            return

        if u.startswith("SEND PEO VALUES"):
            self.peo.send_values()
            autopeotic.progress = "doing PEO"
            return

        if u.startswith("PEO ON"):
            self.peo.on()
            autopeotic.progress = "doing PEO"
            return

        if u.startswith("PEO OFF"):
            self.peo.off()
            return

        # ------------------------------
        # Legacy translations -> Pico text protocol
        # ------------------------------

        # Legacy: WIRE CUT  -> Pico: CUT
        if u.startswith("WIRE CUT"):
            self._send_pico("CUT")
            autopeotic.progress = "cutting wire"
            return

        # Legacy: PUMP1 <ml>  -> Pico: CH1 DISP <ml>
        # Legacy: PUMP2 <ml>  -> Pico: CH2 DISP <ml>
        # Legacy: PUMP3 <ml>  -> Pico: CH3 DISP <ml>
        # Legacy: PUMP4 <ml>  -> Pico: CH4 DISP <ml>
        if u.startswith(("PUMP1 ", "PUMP2 ", "PUMP3 ", "PUMP4 ")):
            parts = instruction.split(maxsplit=1)
            if len(parts) != 2:
                print(f'ERROR instruction "{instruction}" bad PUMPx format in line {line_no}')
                return
            pump_tag = parts[0].upper()  # PUMP1
            ml = parts[1].strip()
            ch = pump_tag.replace("PUMP", "CH")  # PUMP1 -> CH1
            self._send_pico(f"{ch} DISP {ml}")
            autopeotic.progress = "pumping"
            return

        # Legacy: PUMP SOLUTION ...  -> Pico supports SOLUTION <total_ml> CHx <r> ...
        # If your instruction.txt already has SOLUTION ..., prefer that and delete legacy.
        if u.startswith("PUMP SOLUTION"):
            # If you used a custom mixing routine on Linux before, you have two choices:
            # 1) Keep Linux mixing logic (compute durations, send CHx DISP ...), or
            # 2) Use Pico SOLUTION command directly.
            #
            # Here we choose (2) only if the line is already in Pico SOLUTION format after PUMP SOLUTION.
            tail = instruction[len("PUMP "):].strip()   # "SOLUTION ..."
            # Send "SOLUTION ..." as-is
            self._send_pico(tail)
            autopeotic.progress = "doing PEO"
            return

        # ------------------------------
        # Direct Pico protocol passthrough
        # ------------------------------
        # These should appear in instruction.txt exactly as Pico expects:
        # INIT, HOME ALL, CH1 HOME, CH1 ASP 5, CH1 DISP 5, STATUS, SOLENOID OFF, FLUSH ALL, FAN 10, CUT 3, etc.
        pico_prefixes = (
            "INIT",
            "HOME",
            "STATUS",
            "DEOXIDIZE",
            "DISP_SOL",
            "SOLUTION",
            "FLUSH",
            "SOLENOID",
            "FAN",
            "CUT",
            "CH",
        )

        if u.startswith(pico_prefixes):
            self._send_pico(instruction)
            # Optional progress tagging
            if u.startswith("SOLENOID"):
                autopeotic.progress = "solenoid"
            elif u.startswith("FLUSH"):
                autopeotic.progress = "flushing"
            elif u.startswith("FAN"):
                autopeotic.progress = "drying"
            return

        print(f'ERROR instruction "{instruction}" not recognised in line {line_no}')
