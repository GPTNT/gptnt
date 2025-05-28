#!/bin/bash

# usage: ./stress_test.sh <number_of_rooms> <number_of_players>

NUM_ROOMS=$1
NUM_PLAYERS=$2
DISPLAY_NUM=3

if [[ -z $NUM_ROOMS || $NUM_ROOMS -lt 1 || -z $NUM_PLAYERS || $NUM_PLAYERS -lt 1 ]]; then
	echo "Usage: $0 <number_of_rooms> <number_of_players>"
	exit 1
fi

# track PIDs and names
PIDS=()
NAMES=()

# function to kill all tracked processes
cleanup() {
	echo "STRESS_TEST: Killing all background processes..."
	for pid in "${PIDS[@]}"; do
		kill "$pid" 2>/dev/null
	done
}

# function to run a command and track its PID and name
run_and_track() {
	local name="$1"
	shift
	"$@" &
	local pid=$!
	PIDS+=("$pid")
	NAMES+=("$name")
}

# trap script termination to clean up
trap cleanup EXIT

# run experiment manager (only one instance needed)
echo "STRESS_TEST: Starting experiment manager..."
run_and_track "experiment_manager" env WANDB_RUN_GROUP=STRESS_TEST uv run python ./src/gptnt/entrypoints/run_experiment_manager.py

# start room managers
for ((i = 0; i < NUM_ROOMS; i++)); do
	echo "STRESS_TEST: Starting room manager on DISPLAY=:$DISPLAY_NUM..."
	run_and_track "room_manager_$i" env WANDB_RUN_GROUP=STRESS_TEST DISPLAY=:$DISPLAY_NUM uv run python ./src/gptnt/entrypoints/run_room_manager.py
done

# start players
for ((i = 0; i < NUM_PLAYERS; i++)); do
	echo "STRESS_TEST: Starting expert player $i..."
	run_and_track "expert_player_$i" env WANDB_RUN_GROUP=STRESS_TEST uv run python src/gptnt/entrypoints/run_player.py player=ai/expert model=test_expert
	echo "STRESS_TEST: Starting defuser player $i..."
	run_and_track "defuser_player_$i" env WANDB_RUN_GROUP=STRESS_TEST uv run python src/gptnt/entrypoints/run_player.py player=ai/defuser_window_som model=test_defuser
done

# wait and monitor
for i in "${!PIDS[@]}"; do
	pid="${PIDS[$i]}"
	name="${NAMES[$i]}"

	wait "$pid"
	status=$?
	if [[ $status -ne 0 ]]; then
		echo "STRESS_TEST ERROR: Process '$name' (PID $pid) failed with exit code $status."
		exit 1
	fi
done

echo "STRESS_TEST: All processes ended."
