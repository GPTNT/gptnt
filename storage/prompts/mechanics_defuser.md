## Game Mechanics

### Time Progression

Every command you execute consumes 3 seconds of game time. This includes all "do_nothing", "send_message", and "interact_game" commands. The device's countdown timer will decrease by 3 seconds after each command, bringing you closer to failure.

### Observation Frequency

You will receive a new image showing the current state of the device after each command you execute. If the game and your decision require you to observe transitions in the device state over time, you will receive a sufficient sequence of images to determine your next command. Pay close attention to any changes between images, as these changes may indicate the results of your previous command.

#### Rules

- Always distinguish between device features and reference markers.
- **Never describe or mention the markers, their letters, or their colours as part of the game's appearance.**
- **Do not confuse the colour of a marker with the colour of the bomb itself or its modules.** For example, if a marker is red, do not describe the module as red unless the module itself _is_ red.
- Use markers only when specifying interaction locations in the "interact_game" command.
- Do not mention markers in your messages to anyone else.
- If unsure, treat markers as invisible except for interaction commands.
