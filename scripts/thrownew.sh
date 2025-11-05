#!/bin/bash
set -euo pipefail

DISPLAY_NUM=3

# Header
gum style --foreground 212 --border-foreground 212 --border double --align center --width 60 --margin "1 2" --padding "1 4" "🧀 Throw GPTNT"

# Show configuration
echo ""
gum style --foreground 86 "Configuration:"

# Get parameters with gum input (with defaults from args if provided)
NUM_GAMES=${1:-$(gum input --placeholder "e.g., 3" --value "1" --prompt "How many games? " --width 40)}
echo "  🎮 Games: $(gum style --bold "$NUM_GAMES")"

CLAUDE_PLAYERS=${2:-$(gum input --placeholder "e.g., 4" --value "0" --prompt "How many Claude? " --width 40)}
echo "  🤖 Claude: $(gum style --bold "$CLAUDE_PLAYERS")"

GEMINI_PLAYERS=${3:-$(gum input --placeholder "e.g., 4" --value "0" --prompt "How many Gemini? " --width 40)}
echo "  💎 Gemini: $(gum style --bold "$GEMINI_PLAYERS")"

GPT_PLAYERS=${4:-$(gum input --placeholder "e.g., 4" --value "0" --prompt "How many GPT? " --width 40)}
echo "  ⚡ GPT: $(gum style --bold "$GPT_PLAYERS")"

INTERNVL_PLAYERS=${5:-$(gum input --placeholder "e.g., 4" --value "0" --prompt "How many InternVL? " --width 40)}
echo "  👁️ InternVL: $(gum style --bold "$INTERNVL_PLAYERS")"

QWEN_PLAYERS=${6:-$(gum input --placeholder "e.g., 4" --value "0" --prompt "How many Qwen? " --width 40)}
echo "  🐉 Qwen: $(gum style --bold "$QWEN_PLAYERS")"

TOTAL_PLAYERS=$((CLAUDE_PLAYERS + GEMINI_PLAYERS + GPT_PLAYERS + INTERNVL_PLAYERS + QWEN_PLAYERS))
echo ""
echo "  Total Players: $(gum style --bold "$TOTAL_PLAYERS")"
echo "  Total Games: $(gum style --bold "$NUM_GAMES")"

# Confirm to proceed
gum confirm "🧀 Throw?" || {
	gum style --foreground 214 --bold "⚠️  Launch cancelled"
	exit 0
}

# Create logs directory
LOGS_DIR="./logs/throw_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOGS_DIR"

gum log --structured --level info "📁 Logs directory created" path "$LOGS_DIR"

# Track PIDs and names
PIDS=()
NAMES=()

# Cleanup function
cleanup() {
	gum log --structured --level warn "🛑 Shutting down all processes..."

	for i in "${!PIDS[@]}"; do
		pid="${PIDS[$i]}"
		name="${NAMES[$i]}"

		if ps -p "$pid" >/dev/null 2>&1; then
			gum log --structured --level debug "Terminating $name" pid "$pid"
			kill -TERM -"$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null
		fi
	done

	gum spin --spinner dot --title "Waiting for graceful shutdown (30s for logfire flush)..." -- sleep 35

	# Force kill any remaining
	for pid in "${PIDS[@]}"; do
		if ps -p "$pid" >/dev/null 2>&1; then
			kill -KILL -"$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null
		fi
	done

	gum style --foreground 42 --bold "✅ All processes terminated"
}

# Run and track function
run_and_track() {
	local name="$1"
	shift

	local log_file="$LOGS_DIR/${name}.log"

	setsid env PYTHONUNBUFFERED=1 "$@" >"$log_file" 2>&1 &

	local pid=$!
	PIDS+=("$pid")
	NAMES+=("$name")

	gum log --structured --level info "✨ Started $name" pid "$pid" log "$log_file"
}

# Trap script termination
trap cleanup EXIT INT TERM

# Start experiment manager
echo ""
gum style --border rounded --padding "0 1" --foreground 212 "🎯 Starting Experiment Manager"
gum spin --spinner moon --title "Initializing experiment manager..." -- sleep 1
run_and_track "experiment_manager" env WANDB_RUN_GROUP=THROWING uv run python -u ./src/gptnt/entrypoints/run_experiment_manager.py

gum spin --spinner dot --title "Waiting for experiment manager to initialize..." -- sleep 5

gum style --foreground 42 --bold "✓ Experiment manager running"
echo ""

# Start game managers
gum style --border rounded --padding "0 1" --foreground 86 "🎮 Starting Game Instances"

for ((i = 0; i < NUM_GAMES; i++)); do
	gum log --structured --level info "Starting game instance $i" display ":$DISPLAY_NUM"

	run_and_track "game_$i" env WANDB_RUN_GROUP=THROWING DISPLAY=:$DISPLAY_NUM \
		uv run python -u ./src/gptnt/entrypoints/run_game_instance.py

	gum spin --spinner dot --title "Game $i initializing..." -- sleep 2
done

gum style --foreground 42 --bold "✓ All $NUM_GAMES games running"
echo ""

# Spawn Claude players
if [[ $CLAUDE_PLAYERS -gt 0 ]]; then
	gum style --border rounded --padding "0 1" --foreground 141 "🤖 Starting Claude Players"

	for ((i = 0; i < CLAUDE_PLAYERS; i++)); do
		gum log --structured --level info "Starting Claude player $i"

		run_and_track "claude45_bedrock_$i" env WANDB_RUN_GROUP=THROWING \
			uv run python -u src/gptnt/entrypoints/run_player.py model=claude45_bedrock

		sleep 1
	done

	gum style --foreground 42 --bold "✓ $CLAUDE_PLAYERS Claude players active"
	echo ""
fi

# Spawn Gemini players
if [[ $GEMINI_PLAYERS -gt 0 ]]; then
	gum style --border rounded --padding "0 1" --foreground 51 "💎 Starting Gemini Players"

	for ((i = 0; i < GEMINI_PLAYERS; i++)); do
		gum log --structured --level info "Starting Gemini player $i"

		run_and_track "gemini_25_player_$i" env WANDB_RUN_GROUP=THROWING \
			uv run python -u src/gptnt/entrypoints/run_player.py model=gemini-25

		sleep 1
	done

	gum style --foreground 42 --bold "✓ $GEMINI_PLAYERS Gemini players active"
	echo ""
fi

# Spawn GPT players
if [[ $GPT_PLAYERS -gt 0 ]]; then
	gum style --border rounded --padding "0 1" --foreground 226 "⚡ Starting GPT Players"

	for ((i = 0; i < GPT_PLAYERS; i++)); do
		gum log --structured --level info "Starting GPT player $i"

		run_and_track "gpt5_player_$i" env WANDB_RUN_GROUP=THROWING \
			uv run python -u src/gptnt/entrypoints/run_player.py model=gpt5

		sleep 1
	done

	gum style --foreground 42 --bold "✓ $GPT_PLAYERS GPT players active"
	echo ""
fi

# Spawn InternVL players
if [[ $INTERNVL_PLAYERS -gt 0 ]]; then
	gum style --border rounded --padding "0 1" --foreground 226 "⚡ Starting InternVL Players"

	for ((i = 0; i < INTERNVL_PLAYERS; i++)); do
		gum log --structured --level info "Starting InternVL player $i"

		run_and_track "internvl_player_$i" env WANDB_RUN_GROUP=THROWING \
			uv run python -u src/gptnt/entrypoints/run_player.py model=internvl3

		sleep 1
	done

	gum style --foreground 42 --bold "✓ $INTERNVL_PLAYERS InternVL players active"
	echo ""
fi

# Spawn Qwen players
if [[ $QWEN_PLAYERS -gt 0 ]]; then
	gum style --border rounded --padding "0 1" --foreground 226 "⚡ Starting Qwen Players"

	for ((i = 0; i < QWEN_PLAYERS; i++)); do
		gum log --structured --level info "Starting Qwen player $i"

		run_and_track "qwen_player_$i" env WANDB_RUN_GROUP=THROWING \
			uv run python -u src/gptnt/entrypoints/run_player.py model=qwen25

		sleep 1
	done

	gum style --foreground 42 --bold "✓ $QWEN_PLAYERS Qwen players active"
	echo ""
fi

# All processes started
echo ""
gum style --foreground 212 --border-foreground 212 --border double --align center --width 60 --margin "1 2" --padding "1 4" "🎮 Running!"
echo ""

gum style --foreground 42 --bold "🚀 All systems go"
echo ""
echo "  Total Processes: $(gum style --bold "${#PIDS[@]}")"
echo "  Logs Directory: $(gum style --italic "$LOGS_DIR")"
echo ""

echo ""
gum style --foreground 86 --bold "🎯 Submit Experiments"
echo ""

THROW_OPTION=$(gum choose \
	"Skip - don't throw experiments" \
	"Throw experiments + delete unneeded" \
	"Throw + skip wandb check" \
	--header "Submit experiments to run?")

# Parse the selection and execute
case "$THROW_OPTION" in
"Skip - don't throw experiments")
	gum style --faint "  ⏭️  Skipping experiment submission"
	;;
"Throw experiments + delete unneeded")
	echo ""
	gum style --foreground 214 "🧀 Throwing experiments (with cleanup)..."
	gum log --structured --level info "Submitting experiments to queue" delete_unneeded true
	uv run python src/gptnt/entrypoints/throw_experiments.py --delete-unneeded
	gum style --foreground 42 "  ✓ Experiments submitted"
	;;
"Throw + skip wandb check")
	echo ""
	gum style --foreground 214 "🧀 Throwing experiments (skipping wandb check)..."
	gum log --structured --level info "Submitting experiments to queue" skip_wandb true
	uv run python src/gptnt/entrypoints/throw_experiments.py --skip-wandb
	gum style --foreground 42 "  ✓ Experiments submitted"
	;;
esac
echo ""

gum style --faint "💡 You can safely detach from tmux now"
echo ""

# Monitor processes with status updates
gum log --structured --level info "👀 Monitoring ${#PIDS[@]} processes"

# Wait for all processes in background and monitor
for i in "${!PIDS[@]}"; do
	pid="${PIDS[$i]}"
	name="${NAMES[$i]}"

	wait "$pid" 2>/dev/null
	status=$?

	if [[ $status -ne 0 ]]; then
		gum log --structured --level error "Process failed: $name" pid "$pid" exit_code "$status"
		gum style --foreground 196 --bold "❌ Check logs at: $LOGS_DIR/${name}.log"
		exit 1
	fi

	gum log --structured --level info "Process completed: $name" pid "$pid"
done

# Success
echo ""
gum style --foreground 212 --border-foreground 212 --border double --align center --width 60 --margin "1 2" --padding "1 4" "🌋 It's over"
echo ""
gum style --foreground 42 --bold "✅ All processes ended successfully"
echo ""
echo "  Logs saved to: $(gum style --italic "$LOGS_DIR")"
echo ""
