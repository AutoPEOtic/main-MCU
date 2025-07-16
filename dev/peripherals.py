import serial
import serial.tools.list_ports
from math import ceil
import settings.config as config

class peripheral_communication():
    def __init__(self, description, baudrate):
        self.description = description
        self.baudrate = baudrate
        
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if port.description == self.description:
                self.serial = serial.Serial(port.device, self.baudrate, timeout=1)
                break

    def send_instruction(self, instruction):
        self.serial.write((f'{instruction}\n').encode())
        print(f'Sending: {instruction.strip()}')

    def concentration_mixing(self):
            pump2_duration = (config.desired_concentration * config.chamber_volume) / (config.tank2_concentration * config.flow_rate)
            pump1_duration = ((config.tank2_concentration - config.desired_concentration) * config.chamber_volume) / (config.tank2_concentration * config.flow_rate)

            #convert to format XX,X
            pump1_duration = ceil(pump1_duration*10)
            pump2_duration = ceil(pump2_duration*10)

            if len(str(pump1_duration)) == 1:   pump1_duration = '00' + str(pump1_duration)
            if len(str(pump2_duration)) == 1:   pump2_duration = '00' + str(pump2_duration)
            if len(str(pump1_duration)) == 2:   pump1_duration = '0' + str(pump1_duration)
            if len(str(pump2_duration)) == 2:   pump2_duration = '0' + str(pump2_duration)

            return pump1_duration, pump2_duration