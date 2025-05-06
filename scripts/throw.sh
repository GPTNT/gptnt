#!/bin/bash

# usage: ./stress_test.sh <number_of_rooms> <claude37_bedrock_players> <gemini_25_players> <gpt4o_players>

NUM_ROOMS=$1
CLAUDE_PLAYERS=$2
GEMINI_PLAYERS=$3
GPT4O_PLAYERS=$4
DISPLAY_NUM=3

if [[ -z $NUM_ROOMS || $NUM_ROOMS -lt 1 || -z $CLAUDE_PLAYERS || $CLAUDE_PLAYERS -lt 0 || -z $GEMINI_PLAYERS || $GEMINI_PLAYERS -lt 0 || -z $GPT4O_PLAYERS || $GPT4O_PLAYERS -lt 0 ]]; then
	echo "Usage: $0 <number_of_rooms> <claude37_bedrock_players> <gemini_25_players> <gpt4o_players>"
	exit 1
fi

# track PIDs and names
PIDS=()
NAMES=()

# function to kill all tracked processes
cleanup() {
	echo "THROWING: Killing all background processes..."
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
echo "THROWING: Starting experiment manager..."
run_and_track "experiment_manager" env WANDB_RUN_GROUP=THROWING uv run python ./src/gptnt/entrypoints/run_experiment_manager.py --prod

# Set up trap to clean up on exit
trap 'echo "Script interrupted."; exit 1' INT TERM

MAX_ATTEMPTS=60
count=0

while [ $count -lt $MAX_ATTEMPTS ]; do
	response=$(curl -s -f -m 10 http://localhost:8099/health) # -m 10 sets a 10-second timeout for curl

	if [ "$response" = "true" ]; then
		echo "Success! Received 'true' response."
		# Break out and continue with the script
		break
	else
		echo "Attempt $count/$MAX_ATTEMPTS: Waiting for true response..."
		sleep 5
		count=$((count + 1))
	fi
done

if [ $count -ge $MAX_ATTEMPTS ]; then
	echo "Timeout reached. Failed to get 'true' response."
	exit 1
fi

# Script continues here after successful response
echo "Continuing with the rest of the script..."

# start room managers
for ((i = 0; i < NUM_ROOMS; i++)); do
	echo "THROWING: Starting room manager on DISPLAY=:$DISPLAY_NUM..."
	run_and_track "room_manager_$i" env WANDB_RUN_GROUP=THROWING DISPLAY=:$DISPLAY_NUM uv run python ./src/gptnt/entrypoints/run_room_manager.py
done

# spawn claude37_bedrock players
for ((i = 0; i < CLAUDE_PLAYERS; i++)); do
	echo "THROWING: Starting claude37_bedrock player $i..."
	run_and_track "claude37_bedrock_expert_player_$i" env WANDB_RUN_GROUP=THROWING uv run python src/gptnt/entrypoints/run_player.py player=ai/expert model=claude37_bedrock system_prompt=expert
	run_and_track "claude37_bedrock_defuser_player_$i" env WANDB_RUN_GROUP=THROWING uv run python src/gptnt/entrypoints/run_player.py player=ai/defuser_window_som model=claude37_bedrock system_prompt=defuser
done

# spawn gemini-25 players
for ((i = 0; i < GEMINI_PLAYERS; i++)); do
	echo "THROWING: Starting gemini-25 player $i..."
	run_and_track "gemini_25_expert_player_$i" env WANDB_RUN_GROUP=THROWING uv run python src/gptnt/entrypoints/run_player.py player=ai/expert model=gemini-25 system_prompt=expert
	run_and_track "gemini_25_defuser_player_$i" env WANDB_RUN_GROUP=THROWING uv run python src/gptnt/entrypoints/run_player.py player=ai/defuser_window_som model=gemini-25 system_prompt=defuser
done

# spawn gpt4o players
for ((i = 0; i < GPT4O_PLAYERS; i++)); do
	echo "THROWING: Starting gpt4o player $i..."
	run_and_track "gpt4o_expert_player_$i" env WANDB_RUN_GROUP=THROWING uv run python src/gptnt/entrypoints/run_player.py player=ai/expert model=gpt4o system_prompt=expert
	run_and_track "gpt4o_defuser_player_$i" env WANDB_RUN_GROUP=THROWING uv run python src/gptnt/entrypoints/run_player.py player=ai/defuser_window_som model=gpt4o system_prompt=defuser
done

# wait and monitor
for i in "${!PIDS[@]}"; do
	pid="${PIDS[$i]}"
	name="${NAMES[$i]}"

	wait "$pid"
	status=$?
	if [[ $status -ne 0 ]]; then
		echo "THROWING ERROR: Process '$name' (PID $pid) failed with exit code $status."
		exit 1
	fi
done

echo "THROWING: All processes ended."
