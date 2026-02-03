#!/bin/bash

# usage: ./throw.sh <number_of_rooms> <claude_players> <gemini_25_players> <gpt5_players>

NUM_ROOMS=$1
CLAUDE_PLAYERS=$2
GEMINI_PLAYERS=$3
GPT_PLAYERS=$4
INTERNVL_PLAYERS=$5
QWEN_PLAYERS=$6
DISPLAY_NUM=3

# Create logs directory if it doesn't exist
LOGS_DIR="./logs/throw_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOGS_DIR"

if [[ -z $NUM_ROOMS || $NUM_ROOMS -lt 1 || -z $CLAUDE_PLAYERS || $CLAUDE_PLAYERS -lt 0 || -z $GEMINI_PLAYERS || $GEMINI_PLAYERS -lt 0 || -z $GPT_PLAYERS || $GPT_PLAYERS -lt 0 || -z $INTERNVL_PLAYERS || $INTERNVL_PLAYERS -lt 0 || -z $QWEN_PLAYERS || $QWEN_PLAYERS -lt 0 ]]; then
  echo "Usage: $0 <number_of_rooms> <claude_players> <gemini_players> <gpt_players> <internvl_players> <qwen_players>"
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
    if ps -p "$pid" >/dev/null 2>&1; then
      # Kill the process and all its descendants
      pkill -TERM -P "$pid" 2>/dev/null # Kill children first
      kill -TERM "$pid" 2>/dev/null     # Then parent

      # Also process group
      kill -TERM -"$pid" 2>/dev/null
    fi
  done

  echo "THROWING: Waiting for processes to terminate gracefully (35 secs)..."
  sleep 35

  # Force kill any remaining
  for pid in "${PIDS[@]}"; do
    if ps -p "$pid" >/dev/null 2>&1; then
      pkill -KILL -P "$pid" 2>/dev/null
      kill -KILL "$pid" 2>/dev/null
      kill -KILL -"$pid" 2>/dev/null
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
  setsid env PYTHONUNBUFFERED=1 "$@" >"$log_file" 2>&1 &

  local pid=$!
  PIDS+=("$pid")
  NAMES+=("$name")

  echo "THROWING: Started $name (PID: $pid, Log: $log_file)"
}

# trap script termination to clean up
trap cleanup EXIT INT TERM

# run experiment manager (only one instance needed)
echo "THROWING: Starting experiment manager..."
run_and_track "experiment_manager" env WANDB_RUN_GROUP=THROWING uv run python -u ./src/gptnt/entrypoints/run_experiment_manager.py

sleep 5

# Script continues here after successful response
echo "THROWING: Continuing with the rest of the script..."

# start room managers
for ((i = 0; i < NUM_ROOMS; i++)); do
  echo "THROWING: Starting room manager $i on DISPLAY=:$DISPLAY_NUM..."
  run_and_track "game_$i" env WANDB_RUN_GROUP=THROWING DISPLAY=:$DISPLAY_NUM uv run python -u ./src/gptnt/entrypoints/run_game_instance.py
  sleep 2
done

# spawn claude players
for ((i = 0; i < CLAUDE_PLAYERS; i++)); do
  echo "THROWING: Starting claude player $i..."
  run_and_track "claude_$i" env WANDB_RUN_GROUP=THROWING uv run python -u src/gptnt/entrypoints/run_player.py model=claude45_bedrock
  sleep 1
done

# spawn gemini players
for ((i = 0; i < GEMINI_PLAYERS; i++)); do
  echo "THROWING: Starting gemini player $i..."
  run_and_track "gemini_player_$i" env WANDB_RUN_GROUP=THROWING uv run python -u src/gptnt/entrypoints/run_player.py model=gemini-3
  sleep 1
done

# spawn gpt players
for ((i = 0; i < GPT_PLAYERS; i++)); do
  echo "THROWING: Starting gpt player $i..."
  run_and_track "gpt_player_$i" env WANDB_RUN_GROUP=THROWING uv run python -u src/gptnt/entrypoints/run_player.py model=gpt51-chat
  sleep 1
done

# spawn internvl players
for ((i = 0; i < INTERNVL_PLAYERS; i++)); do
  echo "THROWING: Starting internvl player $i..."
  run_and_track "internvl_player_$i" env WANDB_RUN_GROUP=THROWING uv run python -u src/gptnt/entrypoints/run_player.py model=internvl35
  sleep 1
done

# spawn qwen players
for ((i = 0; i < QWEN_PLAYERS; i++)); do
  echo "THROWING: Starting qwen player $i..."
  run_and_track "qwen_player_$i" env WANDB_RUN_GROUP=THROWING uv run python -u src/gptnt/entrypoints/run_player.py model=qwen3vl
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
