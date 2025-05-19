from communication import stepperCommunication, mainCommunication, spectromterCommunication, peoCommunication
import instructionSender
import database
import config
import time
import os

# Open instructions file
instructions = open(os.path.join('..', 'settings', 'instructions.txt'), "r")

# Initialize communication with devices
stepper = stepperCommunication('stepper', config.stepper_port, config.stepper_baudrate)
main = mainCommunication('main', config.peripheral_pico_port, config.peripheral_pico_baudrate)
spectrum = spectromterCommunication('spectrum', config.spectroscope_port, config.spectroscope_baudrate)
# PEO = peoCommunication(...)  # Uncomment and configure if needed

time.sleep(5)  # Wait for devices to initialize

# Process each instruction line by line
line = 1
for instruction in instructions:
    # Send instruction to the appropriate device
    instructionSender = instructionSender.InstructionSender(main, stepper, spectrum, None)
    instructionSender.send_instruction(instruction, line)

    # If the instruction is 'SPECTRUM GET', get the spectrum and send it to the database
    if instruction.startswith('SPECTRUM GET'):
        spectrum_data = spectrum.getSpectrum()
        voltage = 0  # Replace with actual voltage value
        koh_concentration = 0  # Replace with actual KOH concentration value
        query = database.generate_query(voltage, koh_concentration, spectrum_data)
        database.send(query)

    line += 1