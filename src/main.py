from peripherals import stepperCommunication, mainCommunication, spectromterCommunication, peoCommunication
import instructionSender
import database
import config
import time
import os

# Open instructions file
instructions = open(os.path.join('..', 'settings', 'instructions.txt'), "r")

# Initialize communication with devices
main = mainCommunication('main', config.peripheral_pico_port, config.peripheral_pico_baudrate)
stepper = stepperCommunication('stepper', config.stepper_port, config.stepper_baudrate)
spectrum = spectromterCommunication('spectrum', config.spectroscope_port, config.spectroscope_baudrate)
PEO = peoCommunication('PEO', config.PEO_port, config.PEO_baudrate, config.PEO_parity, config.PEO_stopbits, config.PEO_bytesize, config.PEO_Upos, config.PEO_Ipos, config.PEO_Uneg, config.PEO_Ineg, config.PEO_Pulsepos, config.PEO_Pause1, config.PEO_Pulseneg, config.PEO_Pause2, config.PEO_Multiplier)  # Uncomment and configure if needed

# Initialize database connection
database.init(config.database_host, config.database_user, config.database_password, config.database_name, config.database_port)

time.sleep(2)

# Initialize instruction sender with device references
instructionSender.init_sender(main, stepper, spectrum, PEO)

# Process each instruction line by line
line = 1
for instruction in instructions:
    instructionSender.send_instruction(instruction, line)

    if instruction.startswith('LINE ONE'):
        line = 1
    elif instruction.startswith('SPECTRUM GET'):
        spectrum_data = spectrum.getSpectrum()
        voltage = 0  # Replace with actual voltage value
        koh_concentration = 0  # Replace with actual KOH concentration value

        # Generate query and send it to the database
        query = database.generate_query(config.PEO_Upos, config.desired_concentration, spectrum_data)
        database.send(query)

    line += 1