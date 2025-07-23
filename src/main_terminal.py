from src.autopeotic import autopeotic

autopeotic = autopeotic()

while True:
    for instruction in autopeotic.open_instructions():
        autopeotic.send_instruction(instruction)

        autopeotic.line += 1
    autopeotic.line = 1