#PURPOSE: to send each instruction from instructions.txt to the device that is responsible for executing it
#
#WORKFLOW EXAMPLE:  1) initiates all communication methods
#                   2) opens instructions.txt
#                   3) first istruction is 'G4'
#                   4) recognises that it is a G-code instruction; sends it to stepper arduino via serial
#                   5) waits until the instruction is executed
#                   6) next line is 'SERVO'
#                   7) recognises that this should be executed by main Arduino; sends it to main Arduino via serial
#                   8) and so on...
#
import os
import time
import config
from communication import stepperCommunication, mainCommunication, spectromterCommunication, peoCommunication

#opens instructions file
instructions = open(os.path.join('settings', 'instructions.txt'), "r")

#initialises communication method with each device, at this point __init__() executes for each object
#stepper = stepperCommunication('stepper', config.stepper_port, config.stepper_baudrate)
main = mainCommunication('main', config.peripheral_pico_port, config.peripheral_pico_baudrate)
#spectrum = spectromterCommunication('spectrum', config.spectroscope_port, config.spectroscope_baudrate)
#PEO = peoCommunication('PEO',config.PEO_port,config.PEO_baudrate,config.PEO_parity,config.PEO_stopbits, config.PEO_bytesize,config.PEO_Upos,config.PEO_Ipos,config.PEO_Uneg,config.PEO_Ineg,config.PEO_Pulsepos,config.PEO_Pause1,config.PEO_Pulseneg,config.PEO_Pause2,config.PEO_Multiplier)

time.sleep(5)

#goes through all of the instructions
line = 1
for instruction in instructions:
    #a check to see for which device the instruction is written; then the instruction is sent

    if instruction.startswith('PUMP1'):
        comm, delay = instruction.split(' ')
        main.sendInstruction('a'+delay)

    elif instruction.startswith('PUMP2'):
        comm, delay = instruction.split(' ')
        main.sendInstruction('b'+delay)

    elif instruction.startswith('PUMP3'):
        comm, delay = instruction.split(' ')
        main.sendInstruction('c'+delay)

    elif instruction.startswith('PUMP4'):
        comm, delay = instruction.split(' ')
        main.sendInstruction('d'+delay)

    elif instruction.startswith('SOLENOID'):
        comm, delay = instruction.split(' ')
        main.sendInstruction('c'+delay)

    elif instruction.startswith('FAN'):
        comm, delay = instruction.split(' ')
        main.sendInstruction('f'+delay)

    elif instruction.startswith('WIRE CUT'):
        comm, delay = instruction.split(' ')
        main.sendInstruction('g000')

    elif instruction.startswith(('G1', 'G21', 'G90', 'M30', 'F')):
        stepper.sendInstruction(instruction)

    elif instruction.startswith('PAUSE'):
        pause, delay = instruction.split(' ')
        time.sleep(int(delay)) 

    elif instruction.startswith('SPECTRUM GET'):
        spectrum.getSpectrum()

    elif instruction.startswith('PEO'):
        PEO.sendInstruction(instruction)

    elif instruction.startswith('#'):
        pass

    else:
        print(f'{instruction} not recognised at line:{line}')

    line += 1