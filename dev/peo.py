from pymodbus.client import ModbusSerialClient
import serial
import serial.tools.list_ports
import settings.config as config
import time

class peo_communication():
    def __init__(self, description, baudrate, parity, stopbits, bytesize, Upos, Ipos, Uneg, Ineg, Pulsepos, Pause1, Pulseneg, Pause2, Multiplier):
        self.description = description
        self.baudrate = baudrate
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
                self.serial = ModbusSerialClient(port=port.device,
                                                    baudrate=self.baudrate,
                                                    parity=self.parity,
                                                    stopbits=self.stopbits,
                                                    bytesize=self.bytesize,
                                                )
                self.serial.connect()

    def send_values(self, Upos):
        #COMMENT: for PEO datasheet go to peoDatasheet.txt;

        print("Sending: Update PEO values")
        
        #writing the values to the registers
        self.serial.write_register(address=0, value=int(Upos), slave=20)
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

    def on(self, PEO_time):
        print('Sending: PEO ON')
        self.serial.write_coil(0, True, slave=20)
        print(f"PEO duration: {PEO_time}")
        time.sleep(float(PEO_time))

    def off(self):
        print('Sending: PEO OFF')
        self.serial.write_coil(1, True, slave=20)
