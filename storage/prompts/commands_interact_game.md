### Interact Game

- **Description**: Use to manipulate the bomb based on instructions.

#### Actions Without Location

- **Format**: `<action>{"result": {"kind": "interact_game", "data": {"action": "{GAME_ACTION}"}}}</action>`

##### Valid Actions

- **Rotate Left**: -90° rotation
- **Example**: `<action>{"result": {"kind": "interact_game", "data": {"action": "rotate_left"}}}</action>`
- **Usage**: Use this to rotate the bomb 90° counterclockwise on its local yaw (vertical) axis.

- **Rotate Right**: 90° rotation
- **Example**: `<action>{"result": {"kind": "interact_game", "data": {"action": "rotate_right"}}}</action>`
- **Usage**: Use this to rotate the bomb 90° clockwise on its local yaw (vertical) axis.

- **Flip**: 180° rotation
- **Example**: `<action>{"result": {"kind": "interact_game", "data": {"action": "flip"}}}</action>`
- **Usage**: Use this to rotate the bomb 180° to see the opposite side.

- **Roll Up**: 90° roll upward
- **Example**: `<action>{"result": {"kind": "interact_game", "data": {"action": "roll_up"}}}</action>`
- **Usage**: Use this to roll the bomb upward to see the bottom side. You should not rotate in this position.

- **Roll Down**: 90° roll downward
- **Example**: `<action>{"result": {"kind": "interact_game", "data": {"action": "roll_down"}}}</action>`
- **Usage**: Use this to roll the bomb downward to see the top side. You should not rotate in this position.

- **Zoom Out**: Return to full bomb view from a zoomed module
- **Example**: `<action>{"result": {"kind": "interact_game", "data": {"action": "zoom_out"}}}</action>`
- **Usage**: Use this to return to the full bomb view after zooming in on a module.

- **Release**: Release a hold action
- **Example**: `<action>{"result": {"kind": "interact_game", "data": {"action": "release"}}}</action>`
- **Usage**: Use this to release a button or switch that you've been holding.
