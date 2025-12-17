### Interact Game

- **Description**: Use to manipulate the bomb based on instructions.

#### Actions Without Location

- **Format**: `{"result": {"kind": "interact_game", "data": {"action": "{GAME_ACTION}"}}}`

##### Valid Actions

- **Rotate Left**: -90° rotation
- **Example**: `{"result": {"kind": "interact_game", "data": {"action": "rotate_left"}}}`
- **Usage**: Use this to rotate the bomb 90° counterclockwise on its local yaw (vertical) axis.

- **Rotate Right**: 90° rotation
- **Example**: `{"result": {"kind": "interact_game", "data": {"action": "rotate_right"}}}`
- **Usage**: Use this to rotate the bomb 90° clockwise on its local yaw (vertical) axis.

- **Flip**: 180° rotation
- **Example**: `{"result": {"kind": "interact_game", "data": {"action": "flip"}}}`
- **Usage**: Use this to rotate the bomb 180° to see the opposite side.

- **Roll Up**: 90° roll upward
- **Example**: `{"result": {"kind": "interact_game", "data": {"action": "roll_up"}}}`
- **Usage**: Use this to roll the bomb upward to see the bottom side. You should not rotate in this position.

- **Roll Down**: 90° roll downward
- **Example**: `{"result": {"kind": "interact_game", "data": {"action": "roll_down"}}}`
- **Usage**: Use this to roll the bomb downward to see the top side. You should not rotate in this position.

- **Zoom Out**: Return to full bomb view from a zoomed module
- **Example**: `{"result": {"kind": "interact_game", "data": {"action": "zoom_out"}}}`
- **Usage**: Use this to return to the full bomb view after zooming in on a module.

- **Release**: Release a hold action
- **Example**: `{"result": {"kind": "interact_game", "data": {"action": "release"}}}`
- **Usage**: Use this to release a button or switch that you've been holding.
