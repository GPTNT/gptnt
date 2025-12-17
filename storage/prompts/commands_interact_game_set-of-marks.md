#### Actions With Location

- **Format**: `{"result": {"kind": "interact_game", "data": {"action": "{GAME_ACTION}", "location": "{LOCATION_MARKER}"}}}`

##### Valid Actions

- **Click Release**: Click on location and release immediately
- **Examples**:

  - `{"result": {"kind": "interact_game", "data": {"action": "click_release", "location": "A"}}}`
    - **Usage**: Use this to press and immediately release a module currently in your field of view marked with "A".
  - `{"result": {"kind": "interact_game", "data": {"action": "click_release", "location": "B"}}}`
    - **Usage**: Use this to activate a module currently in your field of view marked with "B" so that you can then see the interactable elements within it. This is essential for proper game mechanics.

- **Hold**: Click and hold on location
- **Examples**:
  - `{"result": {"kind": "interact_game", "data": {"action": "hold", "location": "C"}}}`
    - **Usage**: Use this to press and hold a button currently in your field of view marked with "C". While holding, you may either do_nothing to wait or release to stop holding. No other action may occur until the release.
  - `{"result": {"kind": "interact_game", "data": {"action": "hold", "location": "D"}}}`
    - **Usage**: Use this to press and hold a switch currently in your view marked with "D". While holding, you may either do_nothing to wait or release to stop holding. No other action may occur until the release.
