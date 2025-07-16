from src.autopeotic import autopeotic

autopeotic = autopeotic()

for instruction in autopeotic.open_instructions():
    autopeotic.send_instruction(instruction)

    autopeotic.line += 1