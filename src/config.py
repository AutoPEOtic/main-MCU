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