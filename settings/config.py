import numpy as np

# --------------- CHANGING VARIABLES --------------- #
ime_start = 180      # 3 min
time_stop = 1800      # 30 min
time_amount = 2
time_array = np.linspace(time_start, time_stop, time_amount)

Upos_start = 700
Upos_stop = 700
Upos_amount = 1
Upos_array = np.linspace(Upos_start, Upos_stop, Upos_amount)

KOH_start = 0.1
KOH_stop = 1
KOH_amount = 2
KOH_array = np.linspace(KOH_start, KOH_stop, KOH_amount)

#[peripheral pico]
peripheral_pico_port = "/dev/serial/by-id/usb-MicroPython_Board_in_FS_mode_067758c1fcf370c7-if00"

peripheral_pico_description = "Board in FS mode - Board CDC"
peripheral_pico_baudrate = 115200

#[stepper arduino]
stepper_description = "USB Serial"
stepper_port = "/dev/serial/by-id/usb-1a86_USB2.0-Serial-if00-port0"
stepper_baudrate = 115200

#[spectroscope]
spectroscope_description = "Board in FS mode - Board CDC"
spectroscope_baudrate = 9600

#[PEO]
PEO_description = "USB2.0-Serial"
PEO_baudrate = 19200
PEO_parity = "E"
PEO_stopbits = 1
PEO_bytesize = 8
PEO_Upos = 700
PEO_Ipos = 10
PEO_Uneg = 0
PEO_Ineg = 0
PEO_Pulsepos = 9999
PEO_Pause1 = 20
PEO_Pulseneg = 0
PEO_Pause2 = 0
PEO_Multiplier = 3
PEO_time = 30




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
tank1_concentration = 0  # Distilled water
tank2_concentration = 1  # Concentration of KOH in g/L
desired_concentration = 0.5  # Desired concentration in g/L

flow_rate = 2.26  # Speed of the pump in mL/s at 83% duty cycle
chamber_volume = 17.0  # Volume of the chamber in mL
