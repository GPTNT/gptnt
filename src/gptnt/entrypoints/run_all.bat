start "Experiment Manager" uv run .\src\gptnt\entrypoints\run_experiment_manager.py
start /b uv run .\src\gptnt\entrypoints\run_room_instance.py
start /b uv run .\src\gptnt\entrypoints\run_game_instance.py
start /b uv run .\src\gptnt\entrypoints\run_player.py model=test_expert
start /b uv run .\src\gptnt\entrypoints\run_player.py model=test_defuser
