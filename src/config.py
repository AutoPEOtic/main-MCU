#[main arduino]
peripheral_pico_port = "/dev/ttyACM0"
peripheral_pico_baudrate = 115200

#[stepper arduino]
stepper_port = "/dev/ttyUSB0"
stepper_baudrate = 115200

#[spectroscope]
spectroscope_port = "/dev/ttyACM1"
spectroscope_baudrate = 9600

#[PEO]
PEO_port = "/dev/ttyUSB0"
PEO_baudrate = 19200
PEO_parity = "E"
PEO_stopbits = 1
PEO_bytesize = 8
PEO_Upos = 5
PEO_Ipos = 1
PEO_Uneg = 1
PEO_Ineg = 1
PEO_Pulsepos = 10
PEO_Pause1 = 10
PEO_Pulseneg = 10
PEO_Pause2 = 10
PEO_Multiplier = 3

# [database]
database_host = "localhost"
database_user = "AutoPEOtic"
database_password = "admin"
database_name = "AutoPEOtic_db"
database_port = 3306
# database_table = "measurements"
# database_columns = ["Voltage", "KOH_concentration", "Spectrum"]
# database_values = [0, 0, "spectrum_data"]  # Example values

# [solution]
solution1_concentration = 1.0  # Concentration of solution 1 in g/L
solution2_concentration = 0  # Concentration of solution 2 in g/L
desired_concentration = 0.1  # Desired concentration in g/L

flow_rate = 0.1  # Speed of the pump in mL/s
chamber_volume = 10.0  # Volume of the chamber in mL
