from src.autopeotic import autopeotic
import settings.config as config
autopeotic = autopeotic()

while True:

    for time_value in config.time_array:
        for Upos_value in config.Upos_array:
            for KOH_value in config.KOH_array:
                
                autopeotic.PEO_time = time_value
                autopeotic.Upos = Upos_value
                autopeotic.KOH_concentration = KOH_value                
                
                for instruction in autopeotic.open_instructions():                
                    autopeotic.send_instruction(instruction)

                    autopeotic.line += 1
                autopeotic.count +=1
                autopeotic.line = 1