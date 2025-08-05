from dev.peripherals import peripheral_communication
from dev.peo import peo_communication
from dev.spectrometer import spectrometer_communication
from dev.stepper import stepper_communication

import settings.config as config
from src.sender import sender

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
        #self.PEO_time = config.PEO_time
        #self.KOH_concentration = config.desired_concentration
        #self.Upos = config.PEO_Upos
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
        subprocess.run(['sudo', 'uhubctl', '-a','cycle','-l', '1'])
        subprocess.run(['sudo', 'uhubctl', '-a','cycle','-l', '2'])
        subprocess.run(['sudo', 'uhubctl', '-a','cycle','-l', '3'])
        subprocess.run(['sudo', 'uhubctl', '-a','cycle','-l', '4'])
        time.sleep(5)
        self.peripherals = peripheral_communication(config.peripheral_pico_description, config.peripheral_pico_baudrate)
        self.stepper = stepper_communication(config.stepper_description, config.stepper_baudrate)
        self.spectrum = spectrometer_communication(config.spectroscope_description, config.spectroscope_baudrate)
        self.peo = peo_communication(config.PEO_description, config.PEO_baudrate, config.PEO_parity, config.PEO_stopbits, config.PEO_bytesize, config.PEO_Upos, config.PEO_Ipos, config.PEO_Uneg, config.PEO_Ineg, config.PEO_Pulsepos, config.PEO_Pause1, config.PEO_Pulseneg, config.PEO_Pause2, config.PEO_Multiplier)  # Uncomment and configure if needed
        time.sleep(5)
        self.autopeotic_db = database()
        self.sender = sender(self.peripherals, self.stepper, self.spectrum, self.peo)


    def open_instructions(self):
        instructions = open(os.path.join('settings', 'instructions.txt'), "r")
        return instructions
    
    def send_instruction(self, instruction):
        if instruction.startswith('LINE ONE'):
            self.line = 1

        elif instruction.startswith('RECONNECT'):
            self.connect()
        
        #else: self.sender.send_instruction(self, instruction, self.line)
        #instruction.strip()

        elif instruction=="" or instruction.startswith('#'):  return

        elif instruction.startswith('PUMP'):
            _, delay = instruction.split(' ')
            if instruction.startswith('PUMP1'): self.peripherals.send_instruction('a' + delay); self.progress = "pumping"
            elif instruction.startswith('PUMP2'): self.peripherals.send_instruction('b' + delay); self.progress = "pumping"
            elif instruction.startswith('PUMP3'): self.peripherals.send_instruction('c' + delay); self.progress = "flushing"
            elif instruction.startswith('PUMP4'): self.peripherals.send_instruction('d' + delay)
            elif instruction.startswith('PUMP SOLUTION'):
                pump1_duration, pump2_duration = self.peripherals.concentration_mixing()
                self.progress = "doing PEO"
                self.peripherals.send_instruction('a' + str(pump1_duration)); time.sleep(int(pump1_duration) / 10 + 1)  # Wait for pump1 to finish before starting pump2
                self.peripherals.send_instruction('b' + str(pump2_duration)); time.sleep(int(pump2_duration) / 10 + 1)  # Wait for pump2 to finish

        elif instruction.startswith('SOLENOID'):    _, delay = instruction.split(' '); self.peripherals.send_instruction('e' + delay)
        elif instruction.startswith('FAN'): _, delay = instruction.split(' '); self.peripherals.send_instruction('d' + delay); self.progress = "drying"
        elif instruction.startswith('WIRE CUT'):    self.peripherals.send_instruction('g000'); self.progress = "cutting wire"
        elif instruction.startswith('SPECTRUM GET'):    self.autopeotic_db.send(self.autopeotic_db.generate_query(self.spectrum.get_spectrum())); self.progress = "measuring spectrum"
        elif instruction.startswith(('G1', 'G21', 'G90', 'G91', 'M30', 'F')):   self.stepper.send_instruction(instruction)
        elif instruction.startswith('SEND PEO VALUES'): self.peo.send_values(self.Upos); self.progress = "doing PEO"
        elif instruction.startswith('PEO ON'):  self.peo.on(self.PEO_time); self.progress = "doing PEO"
        elif instruction.startswith('PEO OFF'): self.peo.off()        
        elif instruction.startswith('PAUSE'):   _, delay = instruction.split(' ');  time.sleep(int(delay)/10)
        elif instruction.startswith('MOTOR'):
            _, state = instruction.split(' ')
            if state == "ON":
                self.peripherals.send_instruction('m1')
                self.progress = "motor running"
            elif state == "OFF":
                self.peripherals.send_instruction('m0')
                self.progress = "motor off"
        else: print(f'ERROR instruction "{instruction}" not recognised in line {self.line}')

    def get_spectrum(self):
        return self.spectrum.getSpectrum()