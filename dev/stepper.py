import serial
import serial.tools.list_ports
import settings.config as config
import time

class stepper_communication():
    def __init__(self, description, baudrate):
        self.description = description
        self.baudrate = baudrate

        ports = list(serial.tools.list_ports.comports())
        for port in ports:
            if port.description == self.description:
                self.serial = serial.Serial(port.device, self.baudrate, timeout=1)
                break
        self.__grbl_init()

    def send_instruction(self, instruction):
        self.serial.write((f'{instruction}\n').encode())
        print(f'Sending: {instruction.strip()}')

    def __grbl_init(self):
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
        
        self.serial.write(b'?')
        time.sleep(1)
        response = self.serial.readline().decode().strip()
        print(f'coordinates: {response}')

    def _read_available(self, timeout=0.2):
        """Прочитать все текущие строки из serial (небольшой таймаут)."""
        end = time.time() + timeout
        out = []
        while time.time() < end:
            line = self.serial.readline().decode(errors='ignore').strip()
            if line:
                out.append(line)
            else:
                time.sleep(0.01)
        return out

    def home(self):
        """Запустить процедуру хоминга GRBL по всем осям."""
        self.send_instruction("$H")  # GRBL сам по подключенным концевикам уходит к нулю
        time.sleep(2)                # ждём, пока закончится движение (время зависит от расстояния и скорости)
        self.send_instruction("?")   # запрос текущих координат после хоминга