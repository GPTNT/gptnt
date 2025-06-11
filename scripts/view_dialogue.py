import itertools
import json
import shutil
import warnings
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl
import streamlit as st
import structlog
import wandb

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.ktane.actions import RelativeCoordinate
from gptnt.players.metrics.structures import (
    ActionMetric,
    BombStateMetric,
    DoNothingMetric,
    MessageMetric,
    ObservationMetric,
)
from gptnt.players.observations import ObservationHandler
from gptnt.processors.labels.drawing import AnnotationBackgroundParams, AnnotationTextParams
from gptnt.processors.set_of_marks import MaskDrawingParams, SetOfMarksHandler

# Define set of marks specs (copied from _defuser_som.yaml)
SET_OF_MARKS_PAINTER = SetOfMarksHandler(
    annotation_text_params=AnnotationTextParams(
        font=2, font_scale=0.7, thickness=1, space_between_boxes=2
    ),
    annotation_background_params=AnnotationBackgroundParams(padding=3, alpha=1),
    mask_drawing_params=MaskDrawingParams(
        mask_thickness=1, soft_mask_alpha=0.1, bw_outside_mask=False, mask_highlight_size=None
    ),
    add_labels=True,
    add_mask_outline=True,
    mark_type="alphabet",
)

# Initialize session state
if "dialogue_data_loaded" not in st.session_state:
    st.session_state.dialogue_data_loaded = False
if "dialogue_data" not in st.session_state:
    st.session_state.dialogue_data = {}

wandb_entity = wandb.env.get_entity() or "gptnt"
wandb_project = "for-real"

wandb_api = wandb.Api()

logger = structlog.get_logger()


warnings.filterwarnings("ignore", message=".*st.experimental_user.*")


def fetch_runs(wandb_project: str, game_id: str | None = None) -> list[Any] | None:
    """Fetch runs from Weights & Biases API."""
    try:
        inclusion_criteria = [
            {"state": "finished"},
            {"summary_metrics.hard_crash": False},
            {"tags": {"$nin": ["old"]}},
            {"config.game_id": game_id},
        ]
        return wandb_api.runs(
            f"{wandb_entity}/{wandb_project}", filters={"$and": inclusion_criteria}
        )
    except wandb.errors.CommError as e:
        st.error(f"Communication error with W&B API: {e}")
        return None
    except Exception as e:  # noqa: BLE001
        st.error(f"Error fetching runs: {e}")
        return None


def cleanup_artifact_directory(artifact_dir: str | Path) -> None:
    """Clean up artifact directory."""
    if artifact_dir and Path(artifact_dir).exists():
        try:
            shutil.rmtree(artifact_dir)
            if "debug_mode" in st.session_state and st.session_state.debug_mode:
                st.sidebar.info(f"Cleaned up artifact directory: {artifact_dir}")
        except OSError as cleanup_error:
            if "debug_mode" in st.session_state and st.session_state.debug_mode:
                st.sidebar.warning(f"Failed to clean up artifact directory: {cleanup_error}")


def find_matching_artifact(run, table_name):
    """Find the artifact that matches the given table name."""
    run_tables = run.logged_artifacts()
    for artifact in run_tables:
        if artifact.name.split("-")[-1].split(":")[0] == table_name:
            return artifact
    return None


def handle_cache_cleared_cleanup(artifact):
    """Clean up existing artifact if cache was deliberately cleared."""
    if not st.session_state.get("cache_cleared", False):
        return

    try:
        existing_dir = artifact.download()
        if existing_dir and Path(existing_dir).exists():
            cleanup_artifact_directory(existing_dir)
            if "debug_mode" in st.session_state and st.session_state.debug_mode:
                st.sidebar.info("Cleaned existing artifact before fresh download")
    except Exception as e:  # noqa: BLE001
        if "debug_mode" in st.session_state and st.session_state.debug_mode:
            st.sidebar.warning(f"Could not clean existing artifact: {e}")


def load_table_from_artifact(artifact_dir):
    """Load table data from artifact directory."""
    table_files = list(Path(artifact_dir).glob("**/*.table.json"))

    if not table_files:
        return None

    try:
        with table_files[0].open() as f:
            table_data = json.load(f)

        if "columns" in table_data and "data" in table_data:
            df = pd.DataFrame(table_data["data"], columns=table_data["columns"])
            df["artifact_dir"] = artifact_dir
            return pl.from_pandas(df)
    except json.JSONDecodeError as e:
        if "debug_mode" in st.session_state and st.session_state.debug_mode:
            st.sidebar.error(f"JSON decode error loading table: {e}")

    return None


def load_table_from_history(run, table_name):
    """Fallback to load table from run history."""
    try:
        history = run.history()
        if table_name not in history.columns:
            return None

        table_data = history[table_name].dropna().iloc[0]
        if isinstance(table_data, dict) and "data" in table_data and "columns" in table_data:
            columns = table_data["columns"]
            data = table_data["data"]
            df = pd.DataFrame(data, columns=columns)
            return pl.from_pandas(df)
    except Exception as e:  # noqa: BLE001
        if "debug_mode" in st.session_state and st.session_state.debug_mode:
            st.sidebar.error(f"Error loading from history: {e}")

    return None


def load_wandb_table(run, table_name):
    """Load a W&B table directly from a run object."""
    try:
        # Find matching artifact
        artifact = find_matching_artifact(run, table_name)
        if not artifact:
            return pl.DataFrame()

        # Clean up existing artifacts if cache was cleared
        handle_cache_cleared_cleanup(artifact)

        # Download artifact
        artifact_dir = artifact.download()
        if not artifact_dir:
            return pl.DataFrame()

        # Cache the artifact directory for image loading
        cache_key = f"{run.id}_{table_name}"
        cache_artifact_directory(artifact_dir, cache_key)

        # Try to load from artifact files
        df = load_table_from_artifact(artifact_dir)
        if df is not None:
            return df

        # Fallback to history
        df = load_table_from_history(run, table_name)
        if df is not None:
            return df

        return pl.DataFrame()

    except Exception as e:  # noqa: BLE001
        if "debug_mode" in st.session_state and st.session_state.debug_mode:
            st.sidebar.error(f"Error loading table {table_name}: {e}")
        return pl.DataFrame()


def handle_cache_clearing():
    """Handle cache clearing functionality."""
    button = st.sidebar.button("Clear Cache")
    if button:
        try:
            st.cache_data.clear()
            # Set flag to indicate cache was deliberately cleared
            st.session_state.cache_cleared = True
            st.sidebar.success("Cache cleared successfully!")
        except OSError as e:
            st.sidebar.error(f"Error clearing cache: {e}")
    else:
        # Reset the flag if cache clearing button wasn't pressed
        if "cache_cleared" not in st.session_state:
            st.session_state.cache_cleared = False


def process_run_data(run):
    """Process data from a single W&B run."""
    game_id = run.config["game_id"]
    role = run.config["role"]
    dialogue_data = {"game_id": game_id, f"{role}_run_id": run.id, "role": role}

    if role == "defuser":
        actions_df = load_wandb_table(run, "actions")
        if not actions_df.is_empty():
            dialogue_data["actions"] = actions_df

        observations_df = load_wandb_table(run, "observations")
        if not observations_df.is_empty():
            dialogue_data["observations"] = observations_df

        bomb_state_df = load_wandb_table(run, "bomb_states")
        if not observations_df.is_empty():
            dialogue_data["bomb_states"] = bomb_state_df

    messages_df = load_wandb_table(run, "messages")
    if not messages_df.is_empty():
        dialogue_data["messages"] = messages_df

    do_nothing_df = load_wandb_table(run, "do_nothing_actions")
    if not do_nothing_df.is_empty():
        dialogue_data["do_nothing_actions"] = do_nothing_df

    return dialogue_data


def process_actions_table(actions_df):
    """Process actions table to get counts for each action type."""
    if actions_df.is_empty() or "action" not in actions_df.columns:
        return {}

    try:
        action_counts = actions_df.group_by("action").agg(pl.count().alias("count"))

        action_dict = {
            f"{action}_action_count": int(count)
            for action, count in zip(
                action_counts["action"].to_list(), action_counts["count"].to_list(), strict=False
            )
        }

        return action_dict  # noqa: TRY300
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Error processing actions table: {e}")
        return {}


def process_messages_table(messages_df, role):
    """Process messages table to get statistics."""
    if messages_df.is_empty() or "message" not in messages_df.columns:
        return {}

    try:
        messages_df = messages_df.with_columns(pl.col("message").str.len_chars().alias("length"))

        if len(messages_df) > 0:
            length_sum = messages_df["length"].sum()
            length_mean = messages_df["length"].mean()
            length_min = messages_df["length"].min()
            length_max = messages_df["length"].max()

            message_stats = {
                f"message_length_sum_{role}": length_sum,
                f"message_length_mean_{role}": length_mean,
                f"message_length_min_{role}": length_min,
                f"message_length_max_{role}": length_max,
            }

            return message_stats
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Error processing messages table: {e}")

    return {}


def process_reflections_table(reflections_df, role):
    """Process reflections table to get statistics."""
    if reflections_df.is_empty() or "message" not in reflections_df.columns:
        return {}

    try:
        reflection = reflections_df.select("message").item()
        return {f"reflection_{role}": reflection}  # noqa: TRY300
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Error processing reflections table: {e}")
        return {}


def cache_artifact_directory(artifact_dir: str, identifier: str) -> None:
    """Cache artifact directory for later image loading."""
    if not hasattr(st.session_state, "wandb_artifact_cache"):
        st.session_state.wandb_artifact_cache = {}

    st.session_state.wandb_artifact_cache[identifier] = artifact_dir


def get_bytes_image(image_object, artifact_dir):
    path = artifact_dir.joinpath(image_object["path"])
    return path.read_bytes()


def create_observation_metric(row: dict) -> ObservationMetric:
    """Create ObservationMetric from row data."""
    artifact_dir = Path(row.get("artifact_dir"))
    return ObservationMetric(
        frames=[artifact_dir.joinpath(frame["path"]).read_bytes() for frame in row.get("frames")],
        segm_mask=artifact_dir.joinpath(segm_mask["path"]).read_bytes()
        if (segm_mask := row.get("segmentation_mask"))
        else None,
        som_image=artifact_dir.joinpath(row.get("som_image")["path"]).read_bytes(),
        timestamp=row.get("timestamp", 0.0),
    )


def parse_json_field(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    elif value is None:
        return []
    return value


def create_action_metric(
    action_row: dict, bomb_state_row: dict, observation_row: dict
) -> ActionMetric:
    """Create ActionMetric from row data."""
    rel_coordinates = action_row.get("location")

    segm_mask = observation_row.get("segmentation_mask")
    frames = observation_row.get("frames")[-1]
    artifact_dir = Path(observation_row.get("artifact_dir"))

    bomb_state_row["strikes"] = parse_json_field(bomb_state_row["strikes"])
    bomb_state_row["modules"] = parse_json_field(bomb_state_row["modules"])
    bomb_state_row["widgets"] = parse_json_field(bomb_state_row["widgets"])
    bomb_state = BombStateMetric.model_validate(bomb_state_row)

    if segm_mask is not None and rel_coordinates is not None:
        obsh = ObservationHandler(set_of_marks_painter=SET_OF_MARKS_PAINTER)
        obsh.handle_new_observtion(
            frames=[get_bytes_image(frames, artifact_dir)],
            segmentation=get_bytes_image(segm_mask, artifact_dir),
            bomb_state=bomb_state,
        )
        som_location = obsh.set_of_marks_painter.coordinate_to_mark(
            coordinate=RelativeCoordinate(**rel_coordinates)
        )
    else:
        som_location = None

    return ActionMetric(
        timestamp=action_row.get("timestamp", 0.0),
        location=som_location,
        thoughts=action_row.get("thoughts"),
        action=action_row.get("action"),
    )


def create_message_metric(row: dict, player_role) -> MessageMetric:
    """Create MessageMetric from row data."""
    return MessageMetric(
        timestamp=row.get("timestamp", 0.0),
        role=player_role,
        message=row.get("message", ""),
        thoughts=row.get("thoughts", ""),
    )


def create_do_nothing_metric(row: dict, player_role) -> DoNothingMetric:
    """Create DoNothingMetric from row data."""
    timestamp = row.get("timestamp", 0.0)
    thoughts = row.get("thoughts")

    class MockDoNothingAction:
        def __init__(self, thoughts=None):
            self.thoughts = thoughts

    mock_do_nothing = MockDoNothingAction(thoughts)

    return DoNothingMetric.from_action(
        action=mock_do_nothing, role=player_role, timestamp=timestamp
    )


def process_table_rows(
    table_name: str, df, player_role, bomb_state_df=None, observation_df=None
) -> list:
    """Process rows from a specific table and convert to pydantic objects."""
    metrics = []

    for row_idx, row in enumerate(df.iter_rows(named=True)):
        if table_name == "observations":
            metric = create_observation_metric(row)
        elif table_name == "actions":
            bomb_state_row = (
                bomb_state_df.slice(row_idx, 1).to_dicts()[0]
                if len(bomb_state_df) > row_idx
                else {}
            )
            observation_row = (
                observation_df.slice(row_idx, 1).to_dicts()[0]
                if len(observation_df) > row_idx
                else {}
            )
            metric = create_action_metric(row, bomb_state_row, observation_row)
        elif table_name == "messages":
            metric = create_message_metric(row, player_role)
        elif table_name == "do_nothing_actions":
            metric = create_do_nothing_metric(row, player_role)
        else:
            continue  # Skip unknown table types

        metrics.append(metric)

    return metrics


def process_dialogue_data(dialogue_data: dict) -> None:
    """Process a single dialogue entry and add metrics to ordered_data."""
    processed_data = []

    for player_role, player_data in dialogue_data.items():
        # Skip if player_data is None (case when expert is missing)
        if player_data is None:
            continue

        for table_name, df in player_data.items():
            if table_name in ["game_id", "role"] or not hasattr(df, "iter_rows"):
                continue

            if table_name == "actions":
                # Ensure required dataframes exist before processing actions
                bomb_states_df = player_data.get("bomb_states", pl.DataFrame())
                observations_df = player_data.get("observations", pl.DataFrame())

                metrics = process_table_rows(
                    table_name, df, player_role, bomb_states_df, observations_df
                )
            else:
                metrics = process_table_rows(table_name, df, player_role)
            processed_data.extend(metrics)

    processed_data.sort(key=lambda x: x.timestamp)
    return processed_data


@st.cache_data
def load_and_process_dialogue_data(game_id):
    """Load and process data from Weights & Biases with caching."""
    with st.spinner("Loading and processing data..."):
        runs = fetch_runs(wandb_project, game_id)

        if not runs:
            st.warning(f"No run found for {game_id}")
            return None

        dialogue_data = {run.config["role"]: process_run_data(run) for run in runs}

        # Check if playing alone and handle missing expert data
        if len(runs) == 1 and runs[0].config.get("is_playing_alone", False):
            # Only one run exists and it's playing alone
            pass  # dialogue_data already contains only the defuser data
        elif "expert" not in dialogue_data:
            # Multiple runs but no expert found - this might be an error case
            st.warning("Expected expert data but none found")

        processed_dialogue_data = process_dialogue_data(dialogue_data)
        return processed_dialogue_data


def fetch_and_process_data(game_id=None):
    """Fetch and process data based on criteria."""
    fetch_button = st.sidebar.button("Fetch data!")

    if not fetch_button:
        return False

    st.session_state.dialogue_data_loaded = False
    st.session_state.dialogue_data = st.session_state.dialogue_data

    result = load_and_process_dialogue_data(game_id)

    if result is None:
        st.error("Failed to load or process data")
        return False

    st.session_state.dialogue_data[game_id] = result

    return True


def format_timestamp(timestamp: float) -> str:
    """Format timestamp for display."""
    return f"t={timestamp:.2f}s"


def display_observation_metric(metric: ObservationMetric) -> None:
    """Display an observation metric in chat format."""
    # Display only SoM image
    try:
        # Use ObservationMetric's load_observation_from_bytes function
        som_pil = load_observation_from_bytes(metric.som_image)
        st.image(som_pil, caption=format_timestamp(metric.timestamp))

    except Exception as e:  # noqa: BLE001
        st.write(f"Could not display SoM image: {e}")


def display_action_metric(metric: ActionMetric) -> None:
    """Display an action metric in chat format."""
    st.write(f"**Action** - {format_timestamp(metric.timestamp)}")
    st.write(f"**Action:** `{metric.action}`")
    st.write(f"**Location:** `{metric.location}`")

    if hasattr(metric, "thoughts") and metric.thoughts:
        with st.expander("💭 Thoughts"):
            st.write(metric.thoughts)


def display_message_metric(metric: MessageMetric) -> None:
    """Display a message metric in chat format."""
    st.write(f"**Message** - {format_timestamp(metric.timestamp)}")
    st.write(metric.message)

    if hasattr(metric, "thoughts") and metric.thoughts:
        with st.expander("💭 Thoughts"):
            st.write(metric.thoughts)


def display_do_nothing_metric(metric: DoNothingMetric) -> None:
    """Display a do nothing metric in chat format."""
    # role = str(metric.role).lower() if metric.role else "unknown"
    st.write(f"**Do Nothing** - {format_timestamp(metric.timestamp)}")
    st.write("*No action taken*")

    if hasattr(metric, "thoughts") and metric.thoughts:
        with st.expander("💭 Thoughts"):
            st.write(metric.thoughts)


def display_dialogue_for_game(game_id: str):
    """Display dialogue data for a specific game_id using chat messages."""
    if "dialogue_data" not in st.session_state or not st.session_state.dialogue_data:
        st.warning("No dialogue data available")
        return

    dialogue_events = st.session_state.dialogue_data[game_id]

    if not dialogue_events:
        st.info(f"No dialogue events found for game {game_id}")
        return

    st.subheader(f"Showing dialogue for Game: {game_id}")

    # Check if this is a solo game
    roles_present = {getattr(event, "role", "defuser") for event in dialogue_events}
    if len(roles_present) == 1 and "defuser" in roles_present:
        st.info("🎮 Solo Game - Defuser playing alone")

    grouped_events = itertools.groupby(
        dialogue_events, key=lambda x: getattr(x, "role", "defuser")
    )

    for role, events in grouped_events:
        # Use different styling for solo games
        role_display = "defuser (solo)" if role == "defuser" and len(roles_present) == 1 else role

        with st.container(border=True), st.chat_message(role):
            st.caption(f"Role: {role_display}")
            col1, col2 = st.columns([1, 3])
            for event in events:
                match event:
                    case ObservationMetric():
                        with col1:
                            display_observation_metric(event)
                    case ActionMetric():
                        with col2:
                            display_action_metric(event)
                    case MessageMetric():
                        with col2:
                            display_message_metric(event)
                    case DoNothingMetric():
                        with col2:
                            display_do_nothing_metric(event)
                    case _:
                        # Fallback for unknown event types
                        st.write(f"**Unknown Event Type:** {type(event).__name__}")
                        st.write(f"**Timestamp:** {format_timestamp(event.timestamp)}")
                        st.json(event.model_dump() if hasattr(event, "model_dump") else str(event))


def setup_dialogue_viewer():
    """Setup dialogue viewer controls in sidebar if aggregated by game_id."""
    # Only show if aggregation has been performed and game_id is in groupby columns
    st.sidebar.subheader("Dialogue Viewer")

    show_dialogue_viewer = st.sidebar.checkbox("Show Dialogue Viewer", value=True)

    # Update session state
    st.session_state.show_dialogue_viewer = show_dialogue_viewer

    return show_dialogue_viewer


def main() -> None:
    """Main function for the GPTNT Results Visualizer."""
    # Handle cache clearing
    handle_cache_clearing()

    # Check if data is already loaded or needs to be loaded
    if not st.session_state.get("dialogue_data_loaded", False):
        with st.sidebar:
            game_id = st.text_input("game id", value="3e06fd4b-88c1-4a1f-872e-0c8ded5fcfeb")

        if game_id:
            game_id = game_id.replace('"', "").strip()
        dialogue_data_loaded = fetch_and_process_data(game_id)
        if not dialogue_data_loaded:
            st.info("Please fetch data first using the 'Fetch data!' button in the sidebar.")
            return
        st.session_state.dialogue_game_id = game_id
        st.session_state.dialogue_data_loaded = True

    if st.session_state.dialogue_data_loaded:
        display_dialogue_for_game(game_id=st.session_state.dialogue_game_id)

        # Add button to close dialogue viewer
        if st.button("Close Dialogue Viewer"):
            del st.session_state.dialogue_game_id
            st.rerun()


if __name__ == "__main__":
    main()
