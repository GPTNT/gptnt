#### Actions With Location

- **Format**: `{"result": {"kind": "interact_game", "data": {"action": "{GAME_ACTION}", "location": {"x": <int>, "y": <int>}}}}`
- **Note**: Targets are defined by absolute screen coordinates (`x`, `y`). The maximum resolution is {IMAGE_WIDTH}x{IMAGE_HEIGHT}, with (0,0) at the top-left corner and ({IMAGE_WIDTH},{IMAGE_HEIGHT}) at the bottom-right corner.

##### Valid Actions

- **Click Release**: Click on location and release immediately
- **Examples**:

  - `{"result": {"kind": "interact_game", "data": {"action": "click_release", "location": {"x": 100, "y": 200}}}}`
    - **Usage**: Use this to press and immediately release a module at coordinates x=100 and y=200.
  - `{"result": {"kind": "interact_game", "data": {"action": "click_release", "location": {"x": 340, "y": 220}}}}`
    - **Usage**: Use this to press and immediately release a wire coordinates x=340 and y=220.

- **Hold**: Click and hold on location
- **Examples**:
  - `{"result": {"kind": "interact_game", "data": {"action": "hold", "location": {"x": 100, "y": 200}}}}`
    - **Usage**: Use this to press and hold a button at coordinates x=100 and y=200. While holding, you may either do_nothing to wait or release to stop holding. No other action may occur until the release.
  - `{"result": {"kind": "interact_game", "data": {"action": "hold", "location": {"x": 340, "y": 220}}}}`
    - **Usage**: Use this to press and hold a switch at coordinates x=340 and y=220. While holding, you may either do_nothing to wait or release to stop holding. No other action may occur until the release.
