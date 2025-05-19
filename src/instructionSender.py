import time

class InstructionSender:
    """
    Handles parsing and sending instructions to peripheral devices.
    """

    def __init__(self, main, stepper, spectrum=None, peo=None):
        """
        Initialize with communication objects.
        """
        self.main = main
        self.stepper = stepper
        self.spectrum = spectrum
        self.peo = peo

    def send_instruction(self, instruction, line=0):
        """
        Parses and sends a single instruction to the appropriate device.
        """
        instruction = instruction.strip()
        if not instruction or instruction.startswith('#'):
            return  # Ignore empty lines and comments

        try:
            if instruction.startswith('PUMP1'):
                _, delay = instruction.split(' ')
                self.main.sendInstruction('a' + delay)

            elif instruction.startswith('PUMP2'):
                _, delay = instruction.split(' ')
                self.main.sendInstruction('b' + delay)

            elif instruction.startswith('PUMP3'):
                _, delay = instruction.split(' ')
                self.main.sendInstruction('c' + delay)

            elif instruction.startswith('PUMP4'):
                _, delay = instruction.split(' ')
                self.main.sendInstruction('d' + delay)

            elif instruction.startswith('SOLENOID'):
                _, delay = instruction.split(' ')
                self.main.sendInstruction('c' + delay)

            elif instruction.startswith('FAN'):
                _, delay = instruction.split(' ')
                self.main.sendInstruction('f' + delay)

            elif instruction.startswith('WIRE CUT'):
                self.main.sendInstruction('g000')

            elif instruction.startswith(('G1', 'G21', 'G90', 'M30', 'F')):
                self.stepper.sendInstruction(instruction)

            elif instruction.startswith('PAUSE'):
                _, delay = instruction.split(' ')
                time.sleep(int(delay))

            elif instruction.startswith('SPECTRUM GET'):
                if self.spectrum:
                    self.spectrum.getSpectrum()
                # else: pass

            elif instruction.startswith('PEO'):
                if self.peo:
                    self.peo.sendInstruction(instruction)
                # else: pass

            else:
                print(f'{instruction} not recognised at line:{line}')

        except Exception as e:
            print(f"Error processing instruction at line {line}: {instruction}\n{e}")