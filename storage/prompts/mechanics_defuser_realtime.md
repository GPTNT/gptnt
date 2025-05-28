## Game Mechanics

### Time Progression

Every command you execute consumes game time in real time, bringing you closer to detonation. This includes all "do_nothing", "send_message", and "interact_game" commands. How much the bomb's countdown timer will decrease after each command depends on how long it takes you to formulate your response.

### Observation Frequency

You will receive a new image showing the current state of the bomb after each command you execute. If the game and your decision require you to observe transitions in the bomb state over time, you will receive a sufficient sequence of images to determine your next command. Pay close attention to any changes between images, as these changes may indicate the results of your previous command.

#### Rules

- Always distinguish between bomb features and reference markers.
- **Never describe or mention the markers, their letters, or their colours as part of the bomb's appearance.**
- **Do not confuse the colour of a marker with the colour of the bomb or its modules.** For example, if a marker is red, do not describe the module as red unless the module itself _is_ red.
- Use markers only when specifying interaction locations in the "interact_game" command.
- Do not mention markers in your messages to anyone else.
- If unsure, treat markers as invisible except for interaction commands.
