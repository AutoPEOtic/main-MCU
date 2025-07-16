# in this file are defined classes for communication

import time
import serial
import serial.tools.list_ports
from pymodbus.client import ModbusSerialClient
import config

#defines a parrent class for general communication with devices
class communication:
    def __init__(self, name, description, baudrate):
        self.name = name
        self.description = description
        self.baudrate = baudrate
        #self.serial = serial.Serial(self.port, self.baudrate, timeout=1)

    def sendInstruction(self, instruction):
        raise NotImplementedError
    
    def receiveData():
        raise NotImplementedError





#defines a children class for communication with the main Arduino using serial
class mainCommunication(communication):
    def __init__(self, name, description, baudrate):
        super().__init__(name, description, baudrate)
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if port.description == self.description:
                self.serial = serial.Serial(port.device, self.baudrate, timeout=1)
                break
        

    def sendInstruction(self, instruction):
        self.serial.write((f'{instruction}\n').encode())
        print(f'Sending: {instruction.strip()}')




#defines a children class for communication with the stepper Arduino using serial
class stepperCommunication(communication):
    def __init__(self, name, description, baudrate):
        super().__init__(name, description, baudrate)
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if port.description == self.description:
                self.serial = serial.Serial(port.device, self.baudrate, timeout=1)
                break
        self.__grblInit()

    def sendInstruction(self, instruction):
        self.serial.write((f'{instruction}\n').encode())
        print(f'Sending: {instruction.strip()}')

    def __grblInit(self):
	    #for debugging prints grbl settings
        self.serial.write(b'$$\n')
        time.sleep(1)
        response = self.serial.readline().decode().strip()
        print(f'Settings: {response}')
            
        #unlocks grbl
        self.serial.write(b'$X\n')
        time.sleep(1)
        response = self.serial.readline().decode().strip()
        print(f'Unlock response: {response}')





#defines a children class for communication with spectroscope's raspberry pico using UART
class spectromterCommunication(communication):
    def __init__(self, name, description, baudrate):
        super().__init__(name, description, baudrate)
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if port.description == self.description:
                self.serial = serial.Serial(port.device, self.baudrate, timeout=1)
                break

    def getSpectrum(self):
        #PUROPOSE: to receive an array that contains spectrum data
        #WORKFLOW:  1) an activation command is sent to the pico
        #           2) the pico recieves the byte and executes readSpectrum() function
        #           3) in the meanwhile getSpectrum() function waits for response
        #           4) when finished measuring, pico sends spectrum data in the form of list
        #           5) getSpectrum() command receives answer

        self.serial.write(b'a')
        spectrum = self.serial.readline().decode().strip()  #in this response is spectrum list

        print(f'Response: {spectrum}')
        return spectrum




#defines a children class for communication with PEO using modbus
class peoCommunication(communication):
    def __init__(self, name, description, baudrate, parity, stopbits, bytesize, Upos, Ipos, Uneg, Ineg, Pulsepos, Pause1, Pulseneg, Pause2, Multiplier):
        super().__init__(name, description, baudrate)
        self.parity = parity
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.Upos = Upos
        self.Ipos = Ipos
        self.Uneg = Uneg
        self.Ineg = Ineg
        self.Pulsepos = Pulsepos
        self.Pause1 = Pause1
        self.Pulseneg = Pulseneg
        self.Pause2 = Pause2
        self.Multiplier = config.PEO_Multiplier
        
        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if port.description == self.description:
                self.serial = ModbusSerialClient(
                    method='rtu',
                    port=port.device,
                    baudrate=self.baudrate,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    bytesize=self.bytesize,
                )
                self.serial.connect()

    def sendValues(self):
        #VARIABLES: what do they mean?
        #   Upos
        #   Ipos
        #   Uneg
        #   Ineg
        #   Pulsepos
        #   Pause1
        #   Pulseneg
        #   Pause2
        #   Multiplier
        #
        #COMMENT: for PEO datasheet go to peoDatasheet.txt; for original code go to peo.py
        
        #writing the values to the registers
        self.serial.write_register(address=0, value=self.Upos, slave=20)
        self.serial.write_register(address=1, value=self.Ipos, slave=20)
        self.serial.write_register(address=2, value=self.Uneg, slave=20)
        self.serial.write_register(address=3, value=self.Ineg, slave=20)
        self.serial.write_register(address=4, value=self.Pulsepos, slave=20)
        self.serial.write_register(address=5, value=self.Pause1, slave=20)
        self.serial.write_register(address=6, value=self.Pulseneg, slave=20)
        self.serial.write_register(address=7, value=self.Pause2, slave=20)
        self.serial.write_register(address=8, value=self.Multiplier, slave=20)



        #forcing coils to update the display
        self.serial.write_coil(2, True, slave=20)
        self.serial.write_coil(3, True, slave=20)

        time.sleep(1)

    def on(self):
        #turning on the PEO
        self.serial.write_coil(0, True, slave=20)
    def off(self):
        #turning off the PEO
        self.serial.write_coil(1, True, slave=20)
