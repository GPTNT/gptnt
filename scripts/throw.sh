#!/bin/bash

# usage: ./throw.sh <number_of_rooms> <claude37_bedrock_players> <gemini_25_players> <gpt5_players>

NUM_ROOMS=$1
CLAUDE_PLAYERS=$2
GEMINI_PLAYERS=$3
GPT5_PLAYERS=$4
DISPLAY_NUM=3

# Create logs directory if it doesn't exist
LOGS_DIR="./logs/throw_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOGS_DIR"

if [[ -z $NUM_ROOMS || $NUM_ROOMS -lt 1 || -z $CLAUDE_PLAYERS || $CLAUDE_PLAYERS -lt 0 || -z $GEMINI_PLAYERS || $GEMINI_PLAYERS -lt 0 || -z $GPT5_PLAYERS || $GPT5_PLAYERS -lt 0 ]]; then
  echo "Usage: $0 <number_of_rooms> <claude37_bedrock_players> <gemini_25_players> <gpt5_players>"
  exit 1
fi

echo "THROWING: Logging to $LOGS_DIR"

# track PIDs and names
PIDS=()
NAMES=()

# function to kill all tracked processes and their process groups
cleanup() {
  echo "THROWING: Killing all background processes..."
  for pid in "${PIDS[@]}"; do
    # Kill the entire process group (includes subprocesses like KTANE)
    if ps -p "$pid" > /dev/null 2>&1; then
      # Try to kill process group first
      kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
    fi
  done
  
  # Give processes time to cleanup (+30s for logfire to flush spans)
  sleep 35
  
  # Force kill any remaining
  for pid in "${PIDS[@]}"; do
    if ps -p "$pid" > /dev/null 2>&1; then
      kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
    fi
  done
}

# function to run a command and track its PID and name
# Uses setsid to create new session and detach from controlling terminal
run_and_track() {
  local name="$1"
  shift
  
  local log_file="$LOGS_DIR/${name}.log"
  
  # Run with:
  # - setsid: Creates new session, detaches from controlling terminal
  # - PYTHONUNBUFFERED=1: Force unbuffered output
  # - Redirect stdout/stderr to log file
  # Note: Process runs in new process group, immune to terminal signals
  setsid env PYTHONUNBUFFERED=1 "$@" > "$log_file" 2>&1 &
  
  local pid=$!
  PIDS+=("$pid")
  NAMES+=("$name")
  
  echo "THROWING: Started $name (PID: $pid, Log: $log_file)"
}

# trap script termination to clean up
trap cleanup EXIT

# run experiment manager (only one instance needed)
echo "THROWING: Starting experiment manager..."
run_and_track "experiment_manager" env WANDB_RUN_GROUP=THROWING uv run python -u ./src/gptnt/entrypoints/run_experiment_manager.py

# Set up trap to clean up on exit
trap 'echo "Script interrupted."; exit 1' INT TERM

sleep 5

# Script continues here after successful response
echo "THROWING: Continuing with the rest of the script..."

# start room managers
for ((i = 0; i < NUM_ROOMS; i++)); do
  echo "THROWING: Starting room manager $i on DISPLAY=:$DISPLAY_NUM..."
  run_and_track "game_$i" env WANDB_RUN_GROUP=THROWING DISPLAY=:$DISPLAY_NUM uv run python -u ./src/gptnt/entrypoints/run_game_instance.py
  sleep 2
done

# spawn claude37_bedrock players
for ((i = 0; i < CLAUDE_PLAYERS; i++)); do
  echo "THROWING: Starting claude37_bedrock player $i..."
  run_and_track "claude37_bedrock_$i" env WANDB_RUN_GROUP=THROWING uv run python -u src/gptnt/entrypoints/run_player.py model=claude37_bedrock
  sleep 1
done

# spawn gemini-25 players
for ((i = 0; i < GEMINI_PLAYERS; i++)); do
  echo "THROWING: Starting gemini-25 player $i..."
  run_and_track "gemini_25_player_$i" env WANDB_RUN_GROUP=THROWING uv run python -u src/gptnt/entrypoints/run_player.py model=gemini-25
  sleep 1
done

# spawn gpt5 players
for ((i = 0; i < GPT5_PLAYERS; i++)); do
  echo "THROWING: Starting gpt5 player $i..."
  run_and_track "gpt5_player_$i" env WANDB_RUN_GROUP=THROWING uv run python -u src/gptnt/entrypoints/run_player.py model=gpt5
  sleep 1
done

echo "THROWING: You can safely detach from tmux now."

# Wait and monitor all processes
echo "THROWING: Monitoring ${#PIDS[@]} processes. Logs in: $LOGS_DIR"

for i in "${!PIDS[@]}"; do
  pid="${PIDS[$i]}"
  name="${NAMES[$i]}"

  # Wait for the process
  wait "$pid"
  status=$?
  
  if [[ $status -ne 0 ]]; then
    echo "THROWING ERROR: Process '$name' (PID $pid) failed with exit code $status."
    echo "THROWING ERROR: Check logs at: $LOGS_DIR/${name}.log"
    exit 1
  fi
  
  echo "THROWING: Process '$name' completed successfully."
done

echo "THROWING: All processes ended successfully."
echo "THROWING: Logs saved to: $LOGS_DIR"
