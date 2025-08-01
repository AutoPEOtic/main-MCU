from src.autopeotic import autopeotic
import settings.config as config
import time

autopeotic = autopeotic()
time.sleep(5)
print("You can open the UI")

while True:
    temp_file = open("temp.txt", "r")
    while autopeotic.status == False:
        temp_file.seek(0)
        if temp_file.read() == "ON":
            autopeotic.status = True
            temp_file.close()
        time.sleep(1)

    while autopeotic.status == True:
        for time_value in config.time_array:
            for Upos_value in config.Upos_array:
                for KOH_value in config.KOH_array:

                    autopeotic.PEO_time = time_value
                    autopeotic.Upos = Upos_value
                    autopeotic.KOH_concentration = KOH_value 

                    for instruction in autopeotic.open_instructions():

                        temp_file = open("temp.txt", "w")
                        message = f"{autopeotic.status};{autopeotic.progress};{autopeotic.count};{autopeotic.total_count};{autopeotic.PEO_time};{autopeotic.KOH_concentration};{autopeotic.Upos};{autopeotic.Uneg};{autopeotic.Ipos};{autopeotic.Ineg}"
                        temp_file.truncate(0)
                        temp_file.seek(0)
                        temp_file.write(message)
                        temp_file.close()

                        autopeotic.send_instruction(instruction)            

                        temp_file = open("temp.txt", "r")
                        temp_file.seek(0)
                        if temp_file.read().strip() == "OFF":
                            autopeotic.send_instruction("G1 X0 Y0")
                            autopeotic.send_instruction("PUMP3 100")
                            autopeotic.status = False       
                            break   
                        temp_file.close()

                        autopeotic.line += 1
                    autopeotic.count += 1
                    autopeotic.line = 1