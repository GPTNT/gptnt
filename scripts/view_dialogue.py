# ruff: noqa: FBT001
# flake8: noqa: FBT001
import itertools
import json
import re
import shutil
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import polars as pl
import streamlit as st
import structlog
import wandb
from wandb.apis.public.runs import Runs
from wandb.wandb_run import Run

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.experiments.wandb import get_runs_from_wandb
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

if TYPE_CHECKING:
    from collections.abc import Iterator

# Define set of marks specs (copied from _defuser_som.yaml)
SET_OF_MARKS_PAINTER: SetOfMarksHandler = SetOfMarksHandler(
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

wandb_entity: str = wandb.env.get_entity() or "gptnt"
wandb_project: str = "for-real"

wandb_api: wandb.Api = wandb.Api()

logger = structlog.get_logger()

warnings.filterwarnings("ignore", message=".*st.experimental_user.*")


def extract_run_id(string: str) -> str | None:
    """Extract run ID from an artificat dir name."""
    match = re.search(r"run-([^-]+)", string)
    return match.group(1) if match else None


def get_existing_runs_from_local_dir() -> list[str]:
    """Extract run IDS from artifact directories from local dirs."""
    run_data_dir: Path = Path("wandb/runs")
    if not run_data_dir.exists():
        return []

    run_data_dir_names: list[str] = [
        run_data_dir.name
        for run_data_dir in list(run_data_dir.glob("*/"))
        if run_data_dir.is_dir()
    ]

    run_ids: set[str] = {
        extract_run_id(dir_name)
        for dir_name in run_data_dir_names
        if extract_run_id(dir_name) is not None
    }

    return list(run_ids)


def remove_run_data_from_local(invalid_run_id: str) -> None:
    """Remove run data from local storage."""
    run_dir: Path = Path("wandb/runs") / f"run-{invalid_run_id}"
    shutil.rmtree(run_dir, ignore_errors=True)


def has_all_data(run_id: str) -> bool:
    """Check if a run has all required data."""
    run_dir: Path = Path("wandb/runs") / f"run-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    run_config: dict[str, Any] = load_run_config(run_id)

    # not requiring presence of a "do_nothing_actions" table as it is not always present
    required_tables: list[str] = ["messages", "reflections"]
    if run_config.get("role") == "defuser":
        required_tables.extend(["actions", "observations", "bomb_states"])

    existing_files: list[Path] = list(run_dir.glob("*.json"))
    existing_filenames: list[str] = [file.stem.replace(".table", "") for file in existing_files]

    if "summary" not in existing_filenames or not all(
        table in existing_filenames for table in required_tables
    ):
        remove_run_data_from_local(run_id)
        return False

    return True


def load_run_config(run_id: str) -> dict[str, Any]:
    """Load the configuration for a specific run."""
    config_path: Path = Path(f"wandb/runs/run-{run_id}/config.json")
    if config_path.exists():
        with config_path.open() as f:
            return json.load(f)
    return {}


def is_relevant_run(run_id: str) -> bool:
    """Check if a run matches the given experiment criteria."""
    run_config: dict[str, Any] = load_run_config(run_id)
    if not run_config:
        return False

    return run_config.get("game_id") == st.session_state.dialogue_game_id


def fetch_runs(valid_run_ids: list[str]) -> Runs | None:
    """Fetch runs from Weights & Biases API."""
    try:
        return get_runs_from_wandb(
            f"{wandb_entity}/{wandb_project}",
            additional_filters=[
                {"config.game_id": st.session_state.dialogue_game_id},
                {"config.run_id": {"$nin": valid_run_ids}},
            ],
            timeout=150,
        )
    except wandb.errors.errors.CommError as err:
        headers = err.response.headers
        st.error("Headers: ", headers)
        st.error("Received an error from W&B API. Please try again later.")
        return None


def dump_run_data(run: Run) -> None:
    """Dump the configuration data to a JSON file."""
    run_dir: Path = Path("wandb/runs") / f"run-{run.id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    config_filepath: Path = run_dir / "config.json"
    summary_filepath: Path = run_dir / "summary.json"

    if not config_filepath.exists():
        with config_filepath.open("w") as f:
            json.dump(run.config, f, indent=4)

        if "debug_mode" in st.session_state and st.session_state.debug_mode:
            st.sidebar.info(f"Configuration data dumped to {config_filepath}")

    if not summary_filepath.exists():
        with summary_filepath.open("w") as f:
            json.dump(run.summary_metrics, f, indent=4)

        if "debug_mode" in st.session_state and st.session_state.debug_mode:
            st.sidebar.info(f"Configuration data dumped to {summary_filepath}")


def download_artifacts(run: Run) -> None:
    """Download the artifacts for the run."""
    run_dir: Path = Path("wandb/runs") / f"run-{run.id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Download all artifacts
    for artifact in run.logged_artifacts():
        if "table" in artifact.type:
            artifact.download(root=run_dir)
            if "debug_mode" in st.session_state and st.session_state.debug_mode:
                st.sidebar.info(f"Downloaded artifact: {artifact.name} to {run_dir}")
        else:
            if "debug_mode" in st.session_state and st.session_state.debug_mode:
                st.sidebar.warning(f"Skipping non-table artifact: {artifact.name}")


def maybe_fetch_runs_from_wandb() -> bool:
    existing_run_ids: list[str] = get_existing_runs_from_local_dir()
    relevant_run_ids: list[str] = [
        run_id for run_id in existing_run_ids if is_relevant_run(run_id)
    ]
    valid_run_ids: list[str] = [run_id for run_id in relevant_run_ids if has_all_data(run_id)]
    st.session_state.valid_run_ids = valid_run_ids
    runs: Runs | None = fetch_runs(valid_run_ids)
    if runs and len(runs):
        for run in runs:
            dump_run_data(run)
            download_artifacts(run)
        return True

    if not valid_run_ids and not runs:
        st.warning("No runs found. Please check your criteria or try again later.")

    return False


def load_wandb_table(run_id: str, table_name: str) -> pl.DataFrame:
    """Load a W&B table directly from a run object."""
    run_dir: Path = Path("wandb/runs") / f"run-{run_id}"
    table_filepath: Path = run_dir / f"{table_name}.table.json"
    if not table_filepath.exists():
        return pl.DataFrame()  # Return empty DataFrame if table does not exist
    with table_filepath.open() as f:
        table_data: dict[str, Any] = json.load(f)
    if "columns" in table_data and "data" in table_data:
        df: pd.DataFrame = pd.DataFrame(table_data["data"], columns=table_data["columns"])
        return pl.from_pandas(df)
    return pl.DataFrame()  # Return empty DataFrame if structure is unexpected


def process_run_data(run_id: str) -> dict[str, Any]:
    """Process data from a single W&B run."""
    game_id: str | None = st.session_state.get("dialogue_game_id", None)
    run_config: dict[str, Any] = load_run_config(run_id)
    role: str | None = run_config.get("role")
    dialogue_data: dict[str, Any] = {"game_id": game_id, f"{role}_run_id": run_id, "role": role}

    st.session_state.artifact_dir = Path(f"wandb/runs/run-{run_id}/media/images")

    if role == "defuser":
        actions_df: pl.DataFrame = load_wandb_table(run_id, "actions")
        if not actions_df.is_empty():
            dialogue_data["actions"] = actions_df

        observations_df: pl.DataFrame = load_wandb_table(run_id, "observations")
        if not observations_df.is_empty():
            dialogue_data["observations"] = observations_df

        bomb_state_df: pl.DataFrame = load_wandb_table(run_id, "bomb_states")
        if not observations_df.is_empty():
            dialogue_data["bomb_states"] = bomb_state_df

    messages_df: pl.DataFrame = load_wandb_table(run_id, "messages")
    if not messages_df.is_empty():
        dialogue_data["messages"] = messages_df

    do_nothing_df: pl.DataFrame = load_wandb_table(run_id, "do_nothing_actions")
    if not do_nothing_df.is_empty():
        dialogue_data["do_nothing_actions"] = do_nothing_df

    return dialogue_data


def process_actions_table(actions_df: pl.DataFrame) -> dict[str, int]:
    """Process actions table to get counts for each action type."""
    if actions_df.is_empty() or "action" not in actions_df.columns:
        return {}

    try:
        action_counts: pl.DataFrame = actions_df.group_by("action").agg(pl.count().alias("count"))

        action_dict: dict[str, int] = {
            f"{action}_action_count": int(count)
            for action, count in zip(
                action_counts["action"].to_list(), action_counts["count"].to_list(), strict=False
            )
        }

        return action_dict  # noqa: TRY300
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Error processing actions table: {e}")
        return {}


def process_messages_table(messages_df: pl.DataFrame, role: str) -> dict[str, int | float]:
    """Process messages table to get statistics."""
    if messages_df.is_empty() or "message" not in messages_df.columns:
        return {}

    try:
        messages_df = messages_df.with_columns(pl.col("message").str.len_chars().alias("length"))

        if len(messages_df) > 0:
            length_sum: int = messages_df["length"].sum()
            length_mean: float = messages_df["length"].mean()
            length_min: int = messages_df["length"].min()
            length_max: int = messages_df["length"].max()

            message_stats: dict[str, int | float] = {
                f"message_length_sum_{role}": length_sum,
                f"message_length_mean_{role}": length_mean,
                f"message_length_min_{role}": length_min,
                f"message_length_max_{role}": length_max,
            }

            return message_stats
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Error processing messages table: {e}")

    return {}


def process_reflections_table(reflections_df: pl.DataFrame, role: str) -> dict[str, str]:
    """Process reflections table to get statistics."""
    if reflections_df.is_empty() or "message" not in reflections_df.columns:
        return {}

    try:
        reflection: str = reflections_df.select("message").item()
        return {f"reflection_{role}": reflection}  # noqa: TRY300
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Error processing reflections table: {e}")
        return {}


def get_bytes_image(image_object: dict[str, Any]) -> bytes:
    artifact_dir: Path | None = st.session_state.get("artifact_dir", None)
    if not artifact_dir:
        raise ValueError("Artifact directory not found in session state.")
    path: Path = artifact_dir.joinpath(image_object["path"].split("/")[-1])
    return path.read_bytes()


def create_observation_metric(row: dict[str, Any]) -> ObservationMetric:
    """Create ObservationMetric from row data."""
    return ObservationMetric(
        frames=[get_bytes_image(frame) for frame in row.get("frames")],
        segm_mask=get_bytes_image(segm_mask)
        if (segm_mask := row.get("segmentation_mask"))
        else None,
        som_image=get_bytes_image(row.get("som_image")),
        timestamp=row.get("timestamp", 0.0),
    )


def parse_json_field(value: str | None | list[Any]) -> list[Any]:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
    elif value is None:
        return []
    return value


def create_action_metric(
    action_row: dict[str, Any], bomb_state_row: dict[str, Any], observation_row: dict[str, Any]
) -> ActionMetric:
    """Create ActionMetric from row data."""
    rel_coordinates: dict[str, Any] | None = action_row.get("location")

    segm_mask: dict[str, Any] | None = observation_row.get("segmentation_mask")
    frames: dict[str, Any] = observation_row.get("frames")[-1]

    bomb_state_row["strikes"] = parse_json_field(bomb_state_row["strikes"])
    bomb_state_row["modules"] = parse_json_field(bomb_state_row["modules"])
    bomb_state_row["widgets"] = parse_json_field(bomb_state_row["widgets"])
    bomb_state: BombStateMetric = BombStateMetric.model_validate(bomb_state_row)

    if segm_mask is not None and rel_coordinates is not None:
        obsh: ObservationHandler = ObservationHandler(set_of_marks_painter=SET_OF_MARKS_PAINTER)
        obsh.handle_new_observtion(
            frames=[get_bytes_image(frames)],
            segmentation=get_bytes_image(segm_mask),
            bomb_state=bomb_state,
        )
        som_location: str | None = obsh.set_of_marks_painter.coordinate_to_mark(
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


def create_message_metric(row: dict[str, Any], player_role: str) -> MessageMetric:
    """Create MessageMetric from row data."""
    return MessageMetric(
        timestamp=row.get("timestamp", 0.0),
        role=player_role,
        message=row.get("message", ""),
        thoughts=row.get("thoughts", ""),
    )


def create_do_nothing_metric(row: dict[str, Any], player_role: str) -> DoNothingMetric:
    """Create DoNothingMetric from row data."""
    timestamp: float = row.get("timestamp", 0.0)
    thoughts: str | None = row.get("thoughts")

    class MockDoNothingAction:
        def __init__(self, thoughts: str | None = None) -> None:
            self.thoughts = thoughts

    mock_do_nothing: MockDoNothingAction = MockDoNothingAction(thoughts)

    return DoNothingMetric.from_action(
        action=mock_do_nothing, role=player_role, timestamp=timestamp
    )


def process_table_rows(
    table_name: str,
    df: pl.DataFrame,
    player_role: str,
    bomb_state_df: pl.DataFrame | None = None,
    observation_df: pl.DataFrame | None = None,
) -> list[ObservationMetric | ActionMetric | MessageMetric | DoNothingMetric]:
    """Process rows from a specific table and convert to pydantic objects."""
    metrics: list[ObservationMetric | ActionMetric | MessageMetric | DoNothingMetric] = []

    for row_idx, row in enumerate(df.iter_rows(named=True)):
        if table_name == "observations":
            metric = create_observation_metric(row)
        elif table_name == "actions":
            bomb_state_row: dict[str, Any] = (
                bomb_state_df.slice(row_idx, 1).to_dicts()[0]
                if bomb_state_df is not None and len(bomb_state_df) > row_idx
                else {}
            )
            observation_row: dict[str, Any] = (
                observation_df.slice(row_idx, 1).to_dicts()[0]
                if observation_df is not None and len(observation_df) > row_idx
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


def process_dialogue_data(
    dialogue_data: dict[str, Any],
) -> list[ObservationMetric | ActionMetric | MessageMetric | DoNothingMetric]:
    """Process a single dialogue entry and add metrics to ordered_data."""
    processed_data: list[ObservationMetric | ActionMetric | MessageMetric | DoNothingMetric] = []

    for player_role, player_data in dialogue_data.items():
        # Skip if player_data is None (case when expert is missing)
        if player_data is None:
            continue

        for table_name, df in player_data.items():
            if table_name in ["game_id", "role", f"{player_role}_run_id"] or not hasattr(
                df, "iter_rows"
            ):
                continue

            if table_name == "actions":
                # Ensure required dataframes exist before processing actions
                bomb_states_df: pl.DataFrame = player_data.get("bomb_states", pl.DataFrame())
                observations_df: pl.DataFrame = player_data.get("observations", pl.DataFrame())

                metrics = process_table_rows(
                    table_name, df, player_role, bomb_states_df, observations_df
                )
            else:
                metrics = process_table_rows(table_name, df, player_role)
            processed_data.extend(metrics)

    processed_data.sort(key=lambda x: x.timestamp)
    return processed_data


def load_and_process_dialogue_data() -> (
    list[ObservationMetric | ActionMetric | MessageMetric | DoNothingMetric] | None
):
    """Load and process data from Weights & Biases."""
    with st.spinner("Loading and processing data..."):
        unchecked_runs: bool = True
        while unchecked_runs:
            unchecked_runs = maybe_fetch_runs_from_wandb()

        run_ids: list[str] = st.session_state.get("valid_run_ids", [])
        dialogue_data: dict[str, dict[str, Any]] = {}
        for run_id in run_ids:
            dialogue_data[load_run_config(run_id)["role"]] = process_run_data(run_id)

        # Check if playing alone and handle missing expert data
        if len(run_ids) == 1 and load_run_config(run_ids[0]).get("is_playing_alone", False):
            # Only one run exists and it's playing alone
            pass  # dialogue_data already contains only the defuser data
        elif "expert" not in dialogue_data:
            # Multiple runs but no expert found - this might be an error case
            st.warning("Expected expert data but none found")

        processed_dialogue_data: list[
            ObservationMetric | ActionMetric | MessageMetric | DoNothingMetric
        ] = process_dialogue_data(dialogue_data)
        return processed_dialogue_data


def fetch_and_process_data() -> bool:
    """Fetch and process data based on criteria."""
    fetch_button: bool = st.sidebar.button("Fetch data!")

    if not fetch_button:
        return False

    st.session_state.dialogue_data_loaded = False
    game_id: str | None = st.session_state.get("dialogue_game_id", None)
    result: list[ObservationMetric | ActionMetric | MessageMetric | DoNothingMetric] | None = (
        load_and_process_dialogue_data()
    )

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


def display_dialogue_for_game(game_id: str) -> None:
    """Display dialogue data for a specific game_id using chat messages."""
    if "dialogue_data" not in st.session_state or not st.session_state.dialogue_data:
        st.warning("No dialogue data available")
        return

    dialogue_events: list[ObservationMetric | ActionMetric | MessageMetric | DoNothingMetric] = (
        st.session_state.dialogue_data[game_id]
    )

    if not dialogue_events:
        st.info(f"No dialogue events found for game {game_id}")
        return

    st.subheader(f"Showing dialogue for Game: {game_id}")

    # Check if this is a solo game
    roles_present: set[str] = {getattr(event, "role", "defuser") for event in dialogue_events}
    if len(roles_present) == 1 and "defuser" in roles_present:
        st.info("🎮 Solo Game - Defuser playing alone")

    grouped_events: Iterator[
        tuple[str, Iterator[ObservationMetric | ActionMetric | MessageMetric | DoNothingMetric]]
    ] = itertools.groupby(dialogue_events, key=lambda x: getattr(x, "role", "defuser"))

    for role, events in grouped_events:
        # Use different styling for solo games
        role_display: str = (
            "defuser (solo)" if role == "defuser" and len(roles_present) == 1 else role
        )

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


def setup_dialogue_viewer() -> bool:
    """Setup dialogue viewer controls in sidebar if aggregated by game_id."""
    # Only show if aggregation has been performed and game_id is in groupby columns
    st.sidebar.subheader("Dialogue Viewer")

    show_dialogue_viewer: bool = st.sidebar.checkbox("Show Dialogue Viewer", value=True)

    # Update session state
    st.session_state.show_dialogue_viewer = show_dialogue_viewer

    return show_dialogue_viewer


def main() -> None:
    """Main function for the GPTNT Results Visualizer."""
    # Check if data is already loaded or needs to be loaded
    if not st.session_state.get("dialogue_data_loaded", False):
        with st.sidebar:
            game_id: str = st.text_input("game id", value="", placeholder="Enter game ID")

        if game_id:
            game_id = game_id.replace('"', "").strip()
        st.session_state.dialogue_game_id = game_id
        dialogue_data_loaded: bool = fetch_and_process_data()
        if not dialogue_data_loaded:
            st.info("Please fetch data first using the 'Fetch data!' button in the sidebar.")
            return
        st.session_state.dialogue_data_loaded = True

    if st.session_state.dialogue_data_loaded:
        display_dialogue_for_game(game_id=st.session_state.dialogue_game_id)

        # Add button to close dialogue viewer
        if st.button("Close Dialogue Viewer"):
            del st.session_state.dialogue_game_id
            st.rerun()


if __name__ == "__main__":
    main()
