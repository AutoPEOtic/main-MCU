import serial
import serial.tools.list_ports
import settings.config as config

class spectrometer_communication():
    def __init__(self, description, baudrate):
        self.description = description
        self.baudrate = baudrate

        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if port.description == self.description:
                self.serial = serial.Serial(port.device, self.baudrate, timeout=1)
                break

    def get_spectrum(self):
        #PUROPOSE: to receive an array that contains spectrum data
        #WORKFLOW:  1) an activation command is sent to the pico
        #           2) the pico recieves the byte and executes readSpectrum() function
        #           3) in the meanwhile getSpectrum() function waits for response
        #           4) when finished measuring, pico sends spectrum data in the form of list
        #           5) getSpectrum() command receives answer

        self.serial.write(b'a')
        spectrum = self.serial.readline().decode().strip()  #in this response is spectrum list

        print('Sending: GET SPECTRUM')
        return spectrum

    def close(self):
        try:
            if getattr(self, "serial", None):
                self.serial.close()
        except Exception:
            pass
        self.serial = None


