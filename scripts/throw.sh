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
run_and_track "experiment_manager" env uv run python ./src/gptnt/entrypoints/run_experiment_manager.py

# Set up trap to clean up on exit
trap 'echo "Script interrupted."; exit 1' INT TERM

sleep 10

# Script continues here after successful response
echo "Continuing with the rest of the script..."

# start room managers
for ((i = 0; i < NUM_ROOMS; i++)); do
  echo "THROWING: Starting room manager on DISPLAY=:$DISPLAY_NUM..."
  run_and_track "game_$i" env DISPLAY=:$DISPLAY_NUM uv run python ./src/gptnt/entrypoints/run_game_instance.py
  sleep 5
  run_and_track "room_$i" env uv run python ./src/gptnt/entrypoints/run_room_instance.py
  sleep 2
done

# spawn claude37_bedrock players
for ((i = 0; i < CLAUDE_PLAYERS; i++)); do
  echo "THROWING: Starting claude37_bedrock player $i..."
  run_and_track "claude37_bedrock_$i" env WANDB_RUN_GROUP=THROWING uv run python src/gptnt/entrypoints/run_player.py model=claude37_bedrock
  sleep 1
done

# spawn gemini-25 players
for ((i = 0; i < GEMINI_PLAYERS; i++)); do
  echo "THROWING: Starting gemini-25 player $i..."
  run_and_track "gemini_25_player_$i" env WANDB_RUN_GROUP=THROWING uv run python src/gptnt/entrypoints/run_player.py model=gemini-25
  sleep 1
done

# spawn gpt4o players
for ((i = 0; i < GPT4O_PLAYERS; i++)); do
  echo "THROWING: Starting gpt4o player $i..."
  run_and_track "gpt4o_player_$i" env WANDB_RUN_GROUP=THROWING uv run python src/gptnt/entrypoints/run_player.py model=gpt4o
  sleep 1
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