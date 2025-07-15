import time
import config
from math import ceil

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
            _main.sendInstruction('a' + delay*10)

        elif instruction.startswith('PUMP2'):
            _, delay = instruction.split(' ')
            _main.sendInstruction('b' + delay*10)

        elif instruction.startswith('PUMP3'):
            _, delay = instruction.split(' ')
            _main.sendInstruction('c' + delay*10)

        elif instruction.startswith('PUMP4'):
            _, delay = instruction.split(' ')
            _main.sendInstruction('d' + delay*10)
        
        elif instruction.startswith('PUMP SOLUTION'):
            #calculate needed duration in seconds
            pump2_duration = (config.desired_concentration * config.chamber_volume) / (config.tank2_concentration * config.flow_rate)
            pump1_duration = ((config.tank2_concentration - config.desired_concentration) * config.chamber_volume) / (config.tank2_concentration * config.flow_rate)

            #convert to format XX,X
            pump1_duration = ceil(pump1_duration*10)
            pump2_duration = ceil(pump2_duration*10)


            if len(str(pump1_duration)) == 1:
                pump1_duration = '00' + str(pump1_duration)
            if len(str(pump2_duration)) == 1:
                pump2_duration = '00' + str(pump2_duration)

            if len(str(pump1_duration)) == 2:
                pump1_duration = '0' + str(pump1_duration)
            if len(str(pump2_duration)) == 2:
                pump2_duration = '0' + str(pump2_duration)


            _main.sendInstruction('a' + str(pump1_duration))
            time.sleep(int(pump1_duration) / 10 + 1)  # Wait for pump1 to finish before starting pump2
            _main.sendInstruction('b' + str(pump2_duration))
            time.sleep(int(pump2_duration) / 10 + 1)  # Wait for pump2 to finish

        elif instruction.startswith('SOLENOID'):
            _, delay = instruction.split(' ')
            _main.sendInstruction('e' + delay*10)

        elif instruction.startswith('FAN'):
            _, delay = instruction.split(' ')
            _main.sendInstruction('d' + delay*10)

        elif instruction.startswith('WIRE CUT'):
            _main.sendInstruction('g000')

        elif instruction.startswith(('G1', 'G21', 'G90', 'G91', 'M30', 'F')):
            _stepper.sendInstruction(instruction)

        elif instruction.startswith('PAUSE'):
            _, delay = instruction.split(' ')
            time.sleep(int(delay)/10)

        elif instruction.startswith('SPECTRUM GET'):
            if _spectrum:
                _spectrum.getSpectrum()

        elif instruction.startswith('SEND PEO VALUES'):
            print("Sending: Update PEO values")
            if _peo:
                _peo.sendValues()
        elif instruction.startswith('PEO ON'):
            print("Sending: PEO ON")
            _peo.on()
        elif instruction.startswith('PEO OFF'):
            print("Sending: PEO OFF")
            _peo.off()

        else:
            print(f'{instruction} not recognised at line:{line}')

    except Exception as e:
        print(f"Error processing instruction at line {line}: {instruction}\n{e}")