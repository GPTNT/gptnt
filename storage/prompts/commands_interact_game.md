### Interact Game

- **Description**: Use to manipulate the bomb based on instructions.

#### Actions Without Location

- **Format**: `{"command": "interact_game", "action": "{GAME_ACTION}"}`

##### Valid Actions

- **Rotate Left**: -90° rotation
- **Example**: `{"command": "interact_game", "action": "rotate_left"}`
- **Usage**: Use this to rotate the bomb 90° counterclockwise to see a different side.

- **Rotate Right**: 90° rotation
- **Example**: `{"command": "interact_game", "action": "rotate_right"}`
- **Usage**: Use this to rotate the bomb 90° clockwise to see a different side.

- **Flip**: 180° rotation
- **Example**: `{"command": "interact_game", "action": "flip"}`
- **Usage**: Use this to rotate the bomb 180° to see the opposite side.

- **Roll Up**: 90° roll upward
- **Example**: `{"command": "interact_game", "action": "roll_up"}`
- **Usage**: Use this to roll the bomb upward to see the top side.

- **Roll Down**: 90° roll downward
- **Example**: `{"command": "interact_game", "action": "roll_down"}`
- **Usage**: Use this to roll the bomb downward to see the bottom side.

- **Zoom Out**: Return to full bomb view from a zoomed module
- **Example**: `{"command": "interact_game", "action": "zoom_out"}`
- **Usage**: Use this to return to the full bomb view after zooming in on a module.

- **Release**: Release a hold action
- **Example**: `{"command": "interact_game", "action": "release"}`
- **Usage**: Use this to release a button or switch that you've been holding.

#### Actions With Location

- **Format**: `{"command": "interact_game", "action": "{GAME_ACTION}", "location": "{LOCATION}"}`

##### Valid Actions

- **Click Release**: Click on location and release immediately
- **Examples**:

  - `{"command": "interact_game", "action": "click_release", "location": "A"}`
    - **Usage**: Use this to press and immediately release a module currently in your field of view marked with "A".
  - `{"command": "interact_game", "action": "click_release", "location": "B"}`
    - **Usage**: Use this to activate a module currently in your field of view marked with "B" so that you can then see the interactable elements within it. This is essential for proper game mechanics.

- **Hold**: Click and hold on location
- **Examples**:
  - `{"command": "interact_game", "action": "hold", "location": "C"}`
    - **Usage**: Use this to press and hold a button currently in your field of view marked with "C". Must be followed by a release action.
  - `{"command": "interact_game", "action": "hold", "location": "D"}`
    - **Usage**: Use this to press and hold a switch currently in your view marked with "D". Must be followed by a release action.
