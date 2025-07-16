import serial
import serial.tools.list_ports

ports = list(serial.tools.list_ports.comports())

for port in ports:
    print(port.device)
    print(port.description)
    print(port.hwid)
    print(port.vid)
    print(port.pid)
    print(port.serial_number)
    print(port.manufacturer)
    print(port.location)
    print(port.product)
    print(port.interface)
    print('---')
