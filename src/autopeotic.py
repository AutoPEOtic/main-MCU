from dev.peripherals import PeripheralMCU
from dev.peo import peo_communication
from dev.spectrometer import spectrometer_communication
from dev.stepper import stepper_communication

import settings.config as config

import subprocess
import time
import os
from src.database import database

class autopeotic:
    def __init__(self):
        self.connect()
        self.line = 1
        self.status = False
        self.progress = "not running"

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

    def connect(self):
        print("Reconnecting all devices")
        subprocess.run(['sudo', 'uhubctl', '-a', 'cycle', '-l', '1'])
        subprocess.run(['sudo', 'uhubctl', '-a', 'cycle', '-l', '2'])
        subprocess.run(['sudo', 'uhubctl', '-a', 'cycle', '-l', '3'])
        subprocess.run(['sudo', 'uhubctl', '-a', 'cycle', '-l', '4'])
        time.sleep(5)

        self.peripherals = PeripheralMCU(
            description=config.peripheral_pico_description,
            baudrate=config.peripheral_pico_baudrate,
            port=config.peripheral_pico_port,
        )
        self.peripherals = PeripheralMCU(config.peripheral_pico_description, config.peripheral_pico_baudrate)

        self.stepper = stepper_communication(config.stepper_description, config.stepper_baudrate)
        self.spectrum = spectrometer_communication(config.spectroscope_description, config.spectroscope_baudrate)
        self.peo = peo_communication(
            config.PEO_description, config.PEO_baudrate, config.PEO_parity, config.PEO_stopbits,
            config.PEO_bytesize, config.PEO_Upos, config.PEO_Ipos, config.PEO_Uneg, config.PEO_Ineg,
            config.PEO_Pulsepos, config.PEO_Pause1, config.PEO_Pulseneg, config.PEO_Pause2,
            config.PEO_Multiplier
        )

        time.sleep(5)
        self.autopeotic_db = database()
        #self.sender = sender(self.peripherals, self.stepper, self.spectrum, self.peo)


    def open_instructions(self):
        return open(os.path.join('settings', 'instructions.txt'), "r")

    # -------------------------
    # Peripheral Pico helpers
    # -------------------------
    def _send_pico(self, cmd: str):
        """
        Send a *text* command to the peripheral Pico.
        PeripheralMCU.send_command() should handle newline + OK/ERR read.
        """
        self.peripherals.send_command(cmd)

    def send_instruction(self, instruction: str):
        instruction = instruction.strip()

        # Ignore empty/comments early
        if not instruction or instruction.startswith('#'):
            return

        # Direct peripheral commands (no prefix)
        if instruction.startswith(("CH", "INIT", "DEOXIDIZE", "SOLENOID", "FLUSH", "SOLUTION", "CUT", "FAN", "STATUS")):
            self.peripherals.send_command(instruction)
            return

        u = instruction.upper()

        # -------------------------
        # Meta control
        # -------------------------
        if u.startswith('LINE ONE'):
            self.line = 1
            return

        if u.startswith('RECONNECT'):
            self.connect()
        
        #else: self.sender.send_instruction(self, instruction, self.line)
        #instruction.strip()

        elif instruction=="" or instruction.startswith('#'):  return
        elif instruction.startswith('SPECTRUM GET'):    self.autopeotic_db.send(self.autopeotic_db.generate_query(self.spectrum.get_spectrum())); self.progress = "measuring spectrum"
        elif instruction.startswith(('G1', 'G21', 'G90', 'G91', 'M30', 'F')):   self.stepper.send_instruction(instruction)
        elif instruction.startswith('SEND PEO VALUES'): self.peo.send_values(self.Upos); self.progress = "doing PEO"
        elif instruction.startswith('PEO ON'):  self.peo.on(self.PEO_time); self.progress = "doing PEO"
        elif instruction.startswith('PEO OFF'): self.peo.off()        
        elif instruction.startswith('PAUSE'):
            instruction = instruction.split(';')[0].strip()
            parts = instruction.split(' ')
            if len(parts) == 2 and parts[1].isdigit():
                _, delay = parts
                time.sleep(int(delay)/10)
            else:
                print(f"Invalid PAUSE instruction: {instruction}")
                return
            try:
                time.sleep(float(parts[1]) / 10.0)
            except Exception:
                print(f"Invalid PAUSE value: {instruction}")
            return

        # -------------------------
        # Stepper commands
        # -------------------------
        if u.startswith(("G1", "G21", "G90", "G91", "M30", "F")):
            self.stepper.send_instruction(instruction)
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

        # -------------------------
        # Legacy aliases -> Pico text protocol
        # -------------------------
        if u.startswith("WIRE CUT"):
            # Pico supports: CUT [reps]
            self._send_pico("CUT")
            self.progress = "cutting wire"
            return

        # Legacy: allow "DISP_SOL CH1 5" -> Pico expects "CH1 DISP_SOL 5"
        if u.startswith("DISP_SOL "):
            parts = instruction.split()
            # DISP_SOL CH1 5
            if len(parts) == 3 and parts[1].upper().startswith("CH"):
                self._send_pico(f"{parts[1]} DISP_SOL {parts[2]}")
                return
            # If already in some other format, just pass through
            self._send_pico(instruction)
            return

        # -------------------------
        # Peripheral Pico passthrough (the real protocol)
        # These must match your Pico mode_serial_control.py
        # -------------------------
        pico_prefixes = (
            "INIT",
            "HOME",        # (Pico side: HOME ALL / CHx HOME)
            "STATUS",
            "DEOXIDIZE",
            "SOLUTION",
            "FLUSH",
            "SOLENOID",
            "FAN",
            "CUT",
            "CH",          # CHx ASP/DISP/DISP_SOL/STATUS/HOME/FLUSH/DEOXIDIZE...
        )

        if u.startswith(pico_prefixes):
            self._send_pico(instruction)
            # Optional progress labeling
            if u.startswith("SOLENOID"):
                self.progress = "solenoid"
            elif u.startswith("FLUSH"):
                self.progress = "flushing"
            elif u.startswith("FAN"):
                self.progress = "drying"
            return

        print(f'ERROR instruction "{instruction}" not recognised in line {self.line}')

    def get_spectrum(self):
        return self.spectrum.getSpectrum()
