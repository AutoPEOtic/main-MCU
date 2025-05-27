import time

# Store device references globally (set by init_sender)
_main = None
_stepper = None
_spectrum = None
_peo = None

def init_sender(main, stepper=None, spectrum=None, peo=None):
    """
    Initialize global device references for instruction sending.
    """
    global _main, _stepper, _spectrum, _peo
    _main = main
    _stepper = stepper
    _spectrum = spectrum
    _peo = peo

def send_instruction(instruction, line=0):
    """
    Parses and sends a single instruction to the appropriate device.
    """
    instruction = instruction.strip()
    if not instruction or instruction.startswith('#'):
        return  # Ignore empty lines and comments

    try:
        if instruction.startswith('PUMP1'):
            _, delay = instruction.split(' ')
            _main.sendInstruction('a' + delay)

        elif instruction.startswith('PUMP2'):
            _, delay = instruction.split(' ')
            _main.sendInstruction('b' + delay)

        elif instruction.startswith('PUMP3'):
            _, delay = instruction.split(' ')
            _main.sendInstruction('c' + delay)

        elif instruction.startswith('PUMP4'):
            _, delay = instruction.split(' ')
            _main.sendInstruction('d' + delay)

        elif instruction.startswith('SOLENOID'):
            _, delay = instruction.split(' ')
            _main.sendInstruction('c' + delay)

        elif instruction.startswith('FAN'):
            _, delay = instruction.split(' ')
            _main.sendInstruction('f' + delay)

        elif instruction.startswith('WIRE CUT'):
            _main.sendInstruction('g000')

        elif instruction.startswith(('G1', 'G21', 'G90', 'M30', 'F')):
            _stepper.sendInstruction(instruction)

        elif instruction.startswith('PAUSE'):
            _, delay = instruction.split(' ')
            time.sleep(int(delay))

        elif instruction.startswith('SPECTRUM GET'):
            if _spectrum:
                _spectrum.getSpectrum()

        elif instruction.startswith('SEND PEO VALUES'):
            if _peo:
                _peo.sendValues()
        elif instruction.startswith('PEO ON'):
            _peo.on()
        elif instruction.startswith('PEO OFF'):
            _peo.off()

        else:
            print(f'{instruction} not recognised at line:{line}')

    except Exception as e:
        print(f"Error processing instruction at line {line}: {instruction}\n{e}")