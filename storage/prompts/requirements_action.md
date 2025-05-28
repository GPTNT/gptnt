### Action Requirements

- Interact with the bomb directly by using the "interact_game" command with the appropriate action whenever you want to manipulate the bomb. Use appropriate navigation actions to see different sides of the bomb for other modules and elements.
- Be careful of getting stuck in a perspective where you cannot return to another side of the bomb, consider which rotation or roll action to use given the current perspective.
- Use the "interact_game" command with the "click_release" action first to zoom in on a module before attempting any interaction. This is essential for proper game mechanics.
- Never use the "zoom_out" action or the "release" action with a location marker. Doing so will cause a validation error and your output will be rejected.
- Perform all physical interactions using the "interact_game" command, never just describe them in messages or thoughts.
- Work efficiently as the bomb timer continues to count down. Excessive deliberation or verbose communication increases the risk of failure.
- Ensure that the specific object you want to interact with has a Location Marker associated with it. If it does not, you cannot interact with from your current perspective. You may first need to zoom into the module using the "click_release" action, or zoom out and then in to another module.
