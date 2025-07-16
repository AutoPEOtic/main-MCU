from dev.peripherals import peripheral_communication
from dev.peo import peo_communication
from dev.spectrometer import spectrometer_communication
from dev.stepper import stepper_communication

import settings.config as config
from src.sender import sender


import subprocess
import time
import os

class autopeotic:
    def __init__(self):
        self.connect()
        self.line = 1

    def connect(self):
        print("Reconnecting all devices")
        subprocess.run(['sudo', 'uhubctl', '-R'])
        time.sleep(2)
        self.peripherals = peripheral_communication(config.peripheral_pico_description, config.peripheral_pico_baudrate)
        self.stepper = stepper_communication(config.stepper_description, config.stepper_baudrate)
        self.spectrum = spectrometer_communication(config.spectroscope_description, config.spectroscope_baudrate)
        self.PEO = peo_communication(config.PEO_description, config.PEO_baudrate, config.PEO_parity, config.PEO_stopbits, config.PEO_bytesize, config.PEO_Upos, config.PEO_Ipos, config.PEO_Uneg, config.PEO_Ineg, config.PEO_Pulsepos, config.PEO_Pause1, config.PEO_Pulseneg, config.PEO_Pause2, config.PEO_Multiplier)  # Uncomment and configure if needed
        time.sleep(2)
        self.sender = sender(self.peripherals, self.stepper, self.spectrum, self.PEO)


    def open_instructions(self):
        instructions = open(os.path.join('settings', 'instructions.txt'), "r")
        return instructions
    
    def send_instruction(self, instruction):
        if instruction.startswith('LINE ONE'):
            self.line = 1

        elif instruction.startswith('RECONNECT'):
            self.connect()
        
        else: self.sender.send_instruction(instruction, self.line)

    def get_spectrum(self):
        return self.spectrum.getSpectrum()