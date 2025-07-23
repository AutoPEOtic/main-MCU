import time
from src.database import database

class sender():
    def __init__(self, peripherals, stepper, spectrum=None,peo=None):
        self.peripherals = peripherals
        self.stepper = stepper
        self.spectrum = spectrum
        self.peo = peo
        self.autopeotic_db = database()
        
    def send_instruction(self, autopeotic, instruction, line):
        instruction.strip()

        if instruction=="" or instruction.startswith('#'):  return

        elif instruction.startswith('PUMP'):
            _, delay = instruction.split(' ')
            if instruction.startswith('PUMP1'): self.peripherals.send_instruction('a' + delay); autopeotic.progress = "pumping"
            elif instruction.startswith('PUMP2'): self.peripherals.send_instruction('b' + delay); autopeotic.progress = "pumping"
            elif instruction.startswith('PUMP3'): self.peripherals.send_instruction('c' + delay); autopeotic.progress = "flushing"
            elif instruction.startswith('PUMP4'): self.peripherals.send_instruction('d' + delay)
            elif instruction.startswith('PUMP SOLUTION'):
                pump1_duration, pump2_duration = self.peripherals.concentration_mixing()
                autopeotic.progress = "doing PEO"
                self.peripherals.send_instruction('a' + str(pump1_duration)); time.sleep(int(pump1_duration) / 10 + 1)  # Wait for pump1 to finish before starting pump2
                self.peripherals.send_instruction('b' + str(pump2_duration)); time.sleep(int(pump2_duration) / 10 + 1)  # Wait for pump2 to finish

        elif instruction.startswith('SOLENOID'):    _, delay = instruction.split(' '); self.peripherals.send_instruction('e' + delay)
        elif instruction.startswith('FAN'): _, delay = instruction.split(' '); self.peripherals.send_instruction('d' + delay); autopeotic.progress = "drying"
        elif instruction.startswith('WIRE CUT'):    self.peripherals.send_instruction('g000'); autopeotic.progress = "cutting wire"
        elif instruction.startswith('SPECTRUM GET'):    self.autopeotic_db.send(self.autopeotic_db.generate_query(self.spectrum.get_spectrum())); autopeotic.progress = "measuring spectrum"
        elif instruction.startswith(('G1', 'G21', 'G90', 'G91', 'M30', 'F')):   self.stepper.send_instruction(instruction)
        elif instruction.startswith('SEND PEO VALUES'): self.peo.send_values(); autopeotic.progress = "doing PEO"
        elif instruction.startswith('PEO ON'):  self.peo.on(); autopeotic.progress = "doing PEO"
        elif instruction.startswith('PEO OFF'): self.peo.off()        
        elif instruction.startswith('PAUSE'):   _, delay = instruction.split(' ');  time.sleep(int(delay)/10)
        else: print(f'ERROR instruction "{instruction}" not recognised in line {line}')