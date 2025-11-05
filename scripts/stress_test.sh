#!/bin/bash

# usage: ./stress_test.sh <number_of_rooms> <number_of_players>

NUM_ROOMS=$1
NUM_PLAYERS=$2
DISPLAY_NUM=3

# Create logs directory if it doesn't exist
LOGS_DIR="./logs/stress_test_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOGS_DIR"

if [[ -z "$NUM_ROOMS" || "$NUM_ROOMS" -lt 1 || -z "$NUM_PLAYERS" || "$NUM_PLAYERS" -lt 1 ]]; then
  echo "Usage: $0 <number_of_rooms> <number_of_players>"
  exit 1
fi

echo "STRESS_TEST: Logging to $LOGS_DIR"

# track PIDs and names
PIDS=()
NAMES=()

# function to kill all tracked processes and their process groups
cleanup() {
  echo "STRESS_TEST: Killing all background processes..."
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
  
  echo "STRESS_TEST: Started $name (PID: $pid, Log: $log_file)"
}

# trap script termination to clean up
trap cleanup EXIT

# start experiment manager
echo "STRESS_TEST: Starting experiment manager..."
run_and_track "experiment_manager" env WANDB_RUN_GROUP=STRESS_TEST uv run python -u src/gptnt/entrypoints/run_experiment_manager.py
sleep 5

# start game and room instances
for ((i = 0; i < NUM_ROOMS; i++)); do
  echo "STRESS_TEST: Starting game instance $i on DISPLAY=:$DISPLAY_NUM..."
  run_and_track "game_instance" env WANDB_RUN_GROUP=STRESS_TEST DISPLAY=:$DISPLAY_NUM uv run python -u src/gptnt/entrypoints/run_game_instance.py
  sleep 1
done

# start players
for ((i = 0; i < NUM_PLAYERS; i++)); do
  echo "STRESS_TEST: Starting expert player $i..."
  run_and_track "expert_player_$i" env WANDB_RUN_GROUP=STRESS_TEST uv run python -u src/gptnt/entrypoints/run_player.py model=test_expert
  sleep 1
  echo "STRESS_TEST: Starting defuser player $i..."
  run_and_track "defuser_player_$i" env WANDB_RUN_GROUP=STRESS_TEST uv run python -u src/gptnt/entrypoints/run_player.py model=test_defuser
  sleep 1
done

# Wait and monitor all processes
# Note: These processes are now in separate sessions, so they won't
# be affected by terminal signals when tmux detaches
echo "STRESS_TEST: Monitoring ${#PIDS[@]} processes. Logs in: $LOGS_DIR"
echo "STRESS_TEST: You can safely detach from tmux now."

for i in "${!PIDS[@]}"; do
  pid="${PIDS[$i]}"
  name="${NAMES[$i]}"

  # Wait for the process
  wait "$pid"
  status=$?
  
  if [[ $status -ne 0 ]]; then
    echo "STRESS_TEST ERROR: Process '$name' (PID $pid) failed with exit code $status."
    echo "STRESS_TEST ERROR: Check logs at: $LOGS_DIR/${name}.log"
    exit 1
  fi
  
  echo "STRESS_TEST: Process '$name' completed successfully."
done

echo "STRESS_TEST: All processes ended successfully."
echo "STRESS_TEST: Logs saved to: $LOGS_DIR"
