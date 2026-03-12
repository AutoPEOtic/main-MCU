from dev.peripherals import peripheral_communication
from dev.peo import peo_communication
from dev.spectrometer import spectrometer_communication
from dev.stepper import stepper_communication

from src.checkpoint import CheckpointManager

import settings.config as config

import subprocess
import time
import os
from src.database import database

class autopeotic:
    def __init__(self):
        self.peripherals = None
        self.stepper = None
        self.spectrum = None
        self.peo = None

        self.connect()
        self.line = 1
        self.status = False
        self.progress = "not running"
        self.cp = CheckpointManager("settings/checkpoint_state.json", "settings/checkpoint_events.log")

        # PEO defaults (some overwritten later)
        self.Uneg = config.PEO_Uneg
        self.Ipos = config.PEO_Ipos
        self.Ineg = config.PEO_Ineg

        # --------------- CHANGING VARIABLES ---------------
        self.total_count = len(config.Upos_array) * len(config.time_array) * len(config.KOH_array)
        self.count = 0
        self.Upos = 0
        self.KOH_concentration = 0
        self.PEO_time = 0
    
    def _safe_close(self, obj, name: str):
        if obj is None:
            return
        try:
            if hasattr(obj, "close"):
                print(f"[RECONNECT] Closing {name}")
                obj.close()
        except Exception as e:
            print(f"[RECONNECT] Failed to close {name}: {e}")

    def connect(self):
        print("[RECONNECT] Reconnecting all devices")

        # 1) Explicitly close old handles first
        self._safe_close(getattr(self, "peripherals", None), "peripherals")
        self._safe_close(getattr(self, "stepper", None), "stepper")
        self._safe_close(getattr(self, "spectrum", None), "spectrum")
        self._safe_close(getattr(self, "peo", None), "peo")

        # Optional: small delay so Linux finishes releasing descriptors
        time.sleep(0.5)

        subprocess.run(['sudo', 'uhubctl', '-a', 'cycle', '-l', '1'])
        subprocess.run(['sudo', 'uhubctl', '-a', 'cycle', '-l', '2'])
        subprocess.run(['sudo', 'uhubctl', '-a', 'cycle', '-l', '3'])
        subprocess.run(['sudo', 'uhubctl', '-a', 'cycle', '-l', '4'])
        time.sleep(5)

        self.peripherals = peripheral_communication(
            port=config.peripheral_pico_port,
            baudrate=config.peripheral_pico_baudrate,
            timeout_s=1.0
        )

        self.stepper = stepper_communication(config.stepper_description, config.stepper_baudrate)
        self.spectrum = spectrometer_communication(config.spectroscope_description, config.spectroscope_baudrate)
        self.peo = peo_communication(
            config.PEO_description, config.PEO_baudrate, config.PEO_parity, config.PEO_stopbits,
            config.PEO_bytesize, config.PEO_Upos, config.PEO_Ipos, config.PEO_Uneg, config.PEO_Ineg,
            config.PEO_Pulsepos, config.PEO_Pause1, config.PEO_Pulseneg, config.PEO_Pause2,
            config.PEO_Multiplier
        )

        time.sleep(1)

        # 5) Peripheral sanity check after stabilization
        try:
            self.peripherals.send_command("STATUS")
            time.sleep(0.2)
        except Exception as e:
            print(f"[RECONNECT] STATUS after reconnect failed: {e}")
            raise

        # 6) Final settle time
        time.sleep(1.0)

        self.autopeotic_db = database()


    def open_instructions(self):
        instructions_path = os.path.join("settings", "instructions.txt")
        self.cp.force_restart_if_not_allowed({"RECONNECT"})
        self.cp.run(instructions_path, execute_line=self.send_instruction)

    # -------------------------
    # Peripheral Pico helpers
    # -------------------------
    def _send_pico(self, cmd: str):
        """
        Send a *text* command to the peripheral Pico.
        PeripheralMCU.send_command() should handle newline + OK/ERR read.
        """
        self.peripherals.send_command(cmd)

    def _pico_timeout(self, instruction_upper: str):
        if instruction_upper.startswith(("HOME", "DEOXIDIZE")):
            return 180.0
        if instruction_upper.startswith("SOLUTION"):
            return 120.0
        if instruction_upper.startswith("FLUSH"):
            return 120.0
        if instruction_upper.startswith("CUT"):
            return 30.0
        return 30.0
        
    def send_instruction(self, instruction: str):
        instruction = instruction.strip()
        u = instruction.upper()

        # Ignore empty/comments early
        if not instruction or instruction.startswith('#'):
            return

        # Direct peripheral commands (no prefix)
        if instruction.startswith(("CH", "INIT", "DEOXIDIZE", "SOLENOID", "FLUSH", "SOLUTION", "CUT", "FAN", "STATUS")):
            self.peripherals.send_command(instruction, reply_timeout_s=self._pico_timeout(u))
            return

        # -------------------------
        # Meta control
        # -------------------------
        if u.startswith('LINE ONE'):
            self.line = 1
            return

        if u.startswith('RECONNECT'):
            self.connect()
            return
        
        #else: self.sender.send_instruction(self, instruction, self.line)
        #instruction.strip()

        if instruction=="" or instruction.startswith('#'):  return
       
        if u.startswith('PAUSE'):
            # allow "PAUSE 010" and ignore trailing ";" comments
            instruction_clean = instruction.split(';')[0].strip()
            parts = instruction_clean.split()
            if len(parts) == 2:
                try:
                    delay = float(parts[1]) / 10.0
                    time.sleep(delay)
                except Exception:
                    print(f"Invalid PAUSE value: {instruction}")
            else:
                print(f"Invalid PAUSE instruction: {instruction}")
            return

        # -------------------------
        # Stepper commands
        # -------------------------
        if u.startswith(("G0", "G1", "G2", "G3")):
            self.stepper.send_motion(instruction)
            return

        # Non-motion GRBL commands: just send
        if u.startswith(("G21", "G90", "G91", "G94", "G54", "M30", "F", "$X")):
            self.stepper.send_gcode(instruction, wait_idle=False)
            return

        if u.startswith("HOME"):
            self.stepper.home()
            self.progress = "homing"
            return

        # -------------------------
        # Spectrum / PEO
        # -------------------------
        if u.startswith('SPECTRUM GET'):
            self.autopeotic_db.send(self.autopeotic_db.generate_query(self.spectrum.get_spectrum()))
            self.progress = "measuring spectrum"
            return

        if u.startswith('SEND PEO VALUES'):
            self.peo.send_values(self.Upos)
            self.progress = "doing PEO"
            return

        if u.startswith('PEO ON'):
            self.peo.on(self.PEO_time)
            self.progress = "doing PEO"
            return

        if u.startswith('PEO OFF'):
            self.peo.off()
            return

        # -------------------------
        # Peripheral Pico: explicit prefix support
        # "SYR <cmd>" avoids conflicts with other systems
        # -------------------------
        if u.startswith("SYR "):
            cmd = instruction[4:].strip()
            if cmd:
                self._send_pico(cmd)
            return

    def get_spectrum(self):
        return self.spectrum.getSpectrum()
