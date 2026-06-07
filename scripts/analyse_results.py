# ruff: noqa: FBT001
# flake8: noqa: FBT001
import json
import re
import shutil
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import polars as pl
import streamlit as st
import structlog
import wandb
from polars.dataframe.frame import DataFrame
from wandb.apis.public.runs import Runs
from wandb.wandb_run import Run

from gptnt.records.wandb_runs import get_runs_from_wandb

# Initialize session state


def maybe_clear_session_state() -> None:
    """Clear session state if the user chooses to do so."""


if "session_just_started" not in st.session_state:
    st.session_state.session_just_started = True
if "results_data_loaded" not in st.session_state:
    st.session_state.results_data_loaded = False
if "df" not in st.session_state:
    st.session_state.df = None
if "aggregate_metrics" not in st.session_state:
    st.session_state.aggregate_metrics = []


wandb_entity: str = wandb.env.get_entity() or "gptnt"
wandb_project: str = "for-real"


logger = structlog.get_logger()


def update_available_options(
    module_types: list[str], comm_styles: list[str], agent_frameworks: list[str]
) -> tuple[list[str], list[str], list[str]]:
    """Update available options based on user selections."""
    available_comm_styles: list[str] = ["Synchronous", "Asynchronous"]
    available_agent_frameworks: list[str] = ["ReAct", "Act", "DReAct", "ReDAct"]
    available_defuser_playing: list[str] = ["With Expert", "Alone"]

    # Update based on Module Type selection
    if "Repeated Modules" in module_types:
        # Repeated Modules forces Sync, ReAct, With Expert
        available_comm_styles = ["Synchronous"]
        available_agent_frameworks = ["ReAct"]
        available_defuser_playing = ["With Expert"]

    # Update based on Communication Style selection
    if "Asynchronous" in comm_styles:
        # Async forces ReAct, With Expert
        available_agent_frameworks = ["ReAct"]
        available_defuser_playing = ["With Expert"]

    # Update based on Agent Framework selection
    if any(framework != "ReAct" for framework in agent_frameworks):
        # Non-ReAct frameworks force With Expert
        available_defuser_playing = ["With Expert"]

    return available_comm_styles, available_agent_frameworks, available_defuser_playing


def validate_selections(
    module_types: list[str],
    comm_styles: list[str],
    agent_frameworks: list[str],
    defuser_playing: list[str],
) -> bool:
    """Validate user selections for compatibility."""
    # Check for Repeated Modules constraints
    if "Repeated Modules" in module_types and "Asynchronous" in comm_styles:
        st.sidebar.warning("Repeated Modules cannot be used with Asynchronous communication")
        return False

    # Check for non-ReAct framework constraints
    if any(framework != "ReAct" for framework in agent_frameworks):
        if any(module_type != "Single Modules" for module_type in module_types):
            st.sidebar.warning("Non-ReAct frameworks can only be used with Single Modules")
            return False
        if "Asynchronous" in comm_styles:
            st.sidebar.warning(
                "Non-ReAct frameworks can only be used with Synchronous communication"
            )
            return False

    # Check for Defuser Playing Alone constraints
    if "Alone" in defuser_playing:
        if any(module_type != "Single Modules" for module_type in module_types):
            st.sidebar.warning("Defuser playing alone can only be used with Single Modules")
            return False
        if "Asynchronous" in comm_styles:
            st.sidebar.warning(
                "Defuser playing alone can only be used with Synchronous communication"
            )
            return False
        if any(framework != "ReAct" for framework in agent_frameworks):
            st.sidebar.warning("Defuser playing alone can only be used with ReAct framework")
            return False

    return True


def build_criteria_from_selections(
    module_types: list[str],
    comm_styles: list[str],
    agent_frameworks: list[str],
    defuser_playing: list[str],
    manual_access: bool | None,
) -> list[dict[str, Any]]:
    """Build W&B query criteria from user selections."""
    criteria: list[dict[str, Any]] = []

    # Module type criteria
    condition_criteria: list[str] = []
    if "Single Modules" in module_types:
        condition_criteria.append("single_module")
    if "Repeated Modules" in module_types:
        condition_criteria.extend(
            ["repeated_modules_2", "repeated_modules_4", "repeated_modules_5"]
        )
    if "Multiple Modules" in module_types:
        condition_criteria.extend(
            ["multiple_modules_2", "multiple_modules_2_front", "multiple_modules_n"]
        )

    criteria.append({"config.condition": {"$in": condition_criteria}})

    # Communication style criteria
    comm_style_values: list[str] = []
    if "Synchronous" in comm_styles:
        comm_style_values.append("sync")
    if "Asynchronous" in comm_styles:
        comm_style_values.append("async")

    criteria.append({"config.communication_style": {"$in": comm_style_values}})

    # Agent framework criteria
    if "ReAct" not in agent_frameworks:
        # If ReAct is not selected, we can just filter for the selected frameworks
        criteria.append(
            {"config.thinking_framework": {"$in": [f.lower() for f in agent_frameworks]}}
        )
    elif any(framework != "ReAct" for framework in agent_frameworks):
        # If ReAct is selected along with others, we need special handling
        non_react_frameworks: list[str] = [f.lower() for f in agent_frameworks if f != "ReAct"]
        criteria.append({"config.thinking_framework": {"$in": non_react_frameworks}})
    else:
        # Only ReAct selected
        criteria.append({"config.thinking_framework": "react"})

    # Defuser playing criteria
    if "Alone" in defuser_playing and "With Expert" not in defuser_playing:
        criteria.append({"config.is_playing_alone": True})
    elif "With Expert" in defuser_playing and "Alone" not in defuser_playing:
        criteria.append({"config.is_playing_alone": False})

    # Manual access criteria (if applicable)
    if manual_access is not None:
        criteria.append({"config.include_manual": manual_access})

    return criteria


def get_custom_criteria() -> list[dict[str, Any]]:
    """Allow users to select individual criteria instead of predefined experiments."""
    # Track which options are available for each selection
    available_module_types: list[str] = ["Single Modules", "Repeated Modules", "Multiple Modules"]

    # Initialize session state for module types
    if "module_types" not in st.session_state:
        st.session_state.module_types = ["Single Modules"]

    # Start with the first selection - Module Type(s)
    module_types: list[str] = st.sidebar.multiselect(
        "Module Type(s)", available_module_types, default=st.session_state.module_types
    )

    # Update session state
    st.session_state.module_types = module_types

    if not module_types:
        st.sidebar.warning("Please select at least one module type")
        return []

    # Get available options based on current selections
    available_comm_styles, available_agent_frameworks, available_defuser_playing = (
        update_available_options(module_types, [], [])
    )

    # Initialize session state for comm styles
    if "comm_styles" not in st.session_state:
        st.session_state.comm_styles = [available_comm_styles[0]] if available_comm_styles else []

    # Communication Style selection
    comm_styles: list[str] = (
        st.sidebar.multiselect(
            "Communication Style(s)", available_comm_styles, default=st.session_state.comm_styles
        )
        if "Repeated Modules" not in module_types
        else ["Synchronous"]
    )

    # Update session state
    st.session_state.comm_styles = comm_styles

    if not comm_styles and "Repeated Modules" not in module_types:
        st.sidebar.warning("Please select at least one communication style")
        return []

    # Update available options based on Communication Style selection
    available_comm_styles, available_agent_frameworks, available_defuser_playing = (
        update_available_options(module_types, comm_styles, [])
    )

    # Initialize session state for agent frameworks
    if "agent_frameworks" not in st.session_state:
        st.session_state.agent_frameworks = (
            [available_agent_frameworks[0]] if available_agent_frameworks else []
        )

    # Agent Framework selection
    agent_frameworks: list[str] = (
        st.sidebar.multiselect(
            "Agent Framework(s)",
            available_agent_frameworks,
            default=st.session_state.agent_frameworks,
        )
        if ("Repeated Modules" not in module_types and "Asynchronous" not in comm_styles)
        else ["ReAct"]
    )

    # Update session state
    st.session_state.agent_frameworks = agent_frameworks

    if (
        not agent_frameworks
        and "Repeated Modules" not in module_types
        and "Asynchronous" not in comm_styles
    ):
        st.sidebar.warning("Please select at least one agent framework")
        return []

    # Update available options based on Agent Framework selection
    available_comm_styles, available_agent_frameworks, available_defuser_playing = (
        update_available_options(module_types, comm_styles, agent_frameworks)
    )

    # Initialize session state for defuser playing
    if "defuser_playing" not in st.session_state:
        st.session_state.defuser_playing = (
            [available_defuser_playing[0]] if available_defuser_playing else []
        )

    # Defuser Playing selection
    defuser_playing: list[str] = (
        st.sidebar.multiselect(
            "Defuser Playing", available_defuser_playing, default=st.session_state.defuser_playing
        )
        if (
            "Repeated Modules" not in module_types
            and "Asynchronous" not in comm_styles
            and all(framework == "ReAct" for framework in agent_frameworks)
        )
        else ["With Expert"]
    )

    # Update session state
    st.session_state.defuser_playing = defuser_playing

    if not defuser_playing:
        st.sidebar.warning("Please select at least one defuser playing option")
        return []

    # Validate the selections
    if not validate_selections(module_types, comm_styles, agent_frameworks, defuser_playing):
        return []

    # Manual Access selection (only if Defuser Playing Alone)
    manual_access: bool | None = None
    if "Alone" in defuser_playing:
        # Initialize session state for manual access
        if "manual_access_options" not in st.session_state:
            st.session_state.manual_access_options = ["Without Manual"]

        manual_access_options: list[str] = st.sidebar.multiselect(
            "Manual Access",
            ["With Manual", "Without Manual"],
            default=st.session_state.manual_access_options,
        )

        # Update session state
        st.session_state.manual_access_options = manual_access_options

        if not manual_access_options:
            st.sidebar.warning("Please select at least one manual access option")
            return []

        if (
            "With Manual" in manual_access_options
            and "Without Manual" not in manual_access_options
        ):
            manual_access = True
        elif (
            "Without Manual" in manual_access_options
            and "With Manual" not in manual_access_options
        ):
            manual_access = False

    # Store in session state for use in fetch_runs
    st.session_state.playing_alone = defuser_playing == ["Alone"]
    st.session_state.manual_access = manual_access

    # Store the user's selections in session state for debugging
    st.session_state.debug_selections = {
        "module_types": module_types,
        "comm_styles": comm_styles,
        "agent_frameworks": agent_frameworks,
        "defuser_playing": defuser_playing,
        "manual_access": manual_access_options if "Alone" in defuser_playing else None,
    }

    # Build the criteria based on all selections
    return build_criteria_from_selections(
        module_types, comm_styles, agent_frameworks, defuser_playing, manual_access
    )


def handle_experiment_1_selection() -> list[dict[str, Any]] | None:
    """Handle experiment 1 specific selections."""
    criteria: list[dict[str, Any]] = [
        {"config.condition": "single_module"},
        {"config.communication_style": "sync"},
    ]

    # Initialize session state for agent framework
    if "agent_framework_exp1" not in st.session_state:
        st.session_state.agent_framework_exp1 = None

    agent_framework: str | None = st.sidebar.selectbox(
        "Agent framework (for default use ReAct)", ("ReAct", "Act", "DReAct", "ReDAct"), index=None
    )

    # Update session state
    st.session_state.agent_framework_exp1 = agent_framework

    if agent_framework:
        criteria.append({"config.thinking_framework": agent_framework.lower()})
        return criteria
    return None


def handle_experiment_3_selection() -> list[dict[str, Any]] | None:
    """Handle experiment 3 specific selections."""
    criteria: list[dict[str, Any]] = [
        {"config.condition": "single_module"},
        {"config.communication_style": "sync"},
        {"config.is_playing_alone": True},
    ]

    st.session_state.playing_alone = True

    # Initialize session state for manual checkbox
    if "manual_exp3" not in st.session_state:
        st.session_state.manual_exp3 = False

    manual: bool = st.sidebar.checkbox("Manual", value=st.session_state.manual_exp3)

    # Update session state
    st.session_state.manual_exp3 = manual

    criteria.append({"config.include_manual": manual})

    return criteria


def get_experiment_criteria(experiment: int) -> list[dict[str, Any]] | None:
    """Get criteria for predefined experiments."""
    if experiment == 1:
        return handle_experiment_1_selection()

    if experiment == 3:
        return handle_experiment_3_selection()

    if experiment == 4:
        return [
            {
                "config.condition": {
                    "$in": ["repeated_modules_2", "repeated_modules_4", "repeated_modules_5"]
                }
            },
            {"config.communication_style": "sync"},
        ]
    if experiment == 5:
        return [
            {
                "config.condition": {
                    "$in": ["multiple_modules_2", "multiple_modules_2_front", "multiple_modules_n"]
                }
            },
            {"config.communication_style": "sync"},
        ]

    if experiment == 6:
        return [
            {
                "config.condition": {
                    "$in": ["multiple_modules_2", "multiple_modules_2_front", "multiple_modules_n"]
                }
            },
            {"config.communication_style": "async"},
        ]
    if experiment == 7:
        return [{"config.condition": "single_module"}, {"config.communication_style": "async"}]
    return [{"config.condition": "single_module"}, {"config.communication_style": "sync"}]


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


def fetch_runs(role: Literal["expert", "defuser"], valid_run_ids: list[str]) -> Runs | None:
    """Fetch runs from Weights & Biases API."""
    try:
        return get_runs_from_wandb(
            f"{wandb_entity}/{wandb_project}",
            additional_filters=[
                {"config.role": role},
                {"config.run_id": {"$nin": valid_run_ids}},
                *st.session_state.experiment_criteria,
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


def format_summary_data(summary_json: Any, role: Literal["defuser", "expert"]) -> dict[str, Any]:
    """Format summary data from W&B API."""
    defuser_include_only_keys: list[str] = [
        "is_solved",
        "is_strike_out",
        "is_timed_out",
        "step",
        "time_remaining",
        "total_modules_solved",
        "total_strikes",
        "total_defuser_actions",
        "total_defuser_do_nothing_actions",
        "total_defuser_messages_sent",
    ]

    expert_include_only_keys: list[str] = [
        "total_expert_do_nothing_actions",
        "total_expert_messages_sent",
    ]

    shared_include_only_keys: list[str] = [
        "total_guardrail_violations",
        "total_invalid_format",
        "total_prompt_truncations",
    ]

    formatted_data: dict[str, Any] = {}
    for key, value in summary_json.items():
        if (
            role == "expert"
            and key not in expert_include_only_keys
            and key not in shared_include_only_keys
        ):
            continue

        if (
            role == "defuser"
            and key not in defuser_include_only_keys
            and key not in shared_include_only_keys
        ):
            continue

        formatted_data[key] = value

    return formatted_data


def format_config_data(
    config_dict: dict[str, Any], role: Literal["defuser", "expert"]
) -> dict[str, Any]:
    """Format configuration data from W&B API."""
    if role == "expert":
        return {"game_id": config_dict["game_id"]}

    include_only_keys: list[str] = [
        "game_id",
        "condition",
        "communication_style",
        "thinking_framework",
        "include_manual",
        "is_playing_alone",
        "include_manual",
        "seed",
        "components",
        "optional_widgets",
        "expert_name",
        "defuser_name",
    ]

    formatted_data: dict[str, Any] = {}
    for key, value in config_dict.items():
        if key not in include_only_keys:
            continue
        if key == "optional_widgets":
            formatted_data["num_widgets"] = value
            continue
        formatted_data[key] = value

    return formatted_data


def load_wandb_table(run_id: str, table_name: str) -> pl.DataFrame | None:
    """Load a W&B table directly from a run object."""
    table_filepath: Path = Path("wandb/runs/") / f"run-{run_id}/{table_name}.table.json"
    with table_filepath.open() as f:
        table_data: dict[str, Any] = json.load(f)
    if "columns" in table_data and "data" in table_data:
        df: pd.DataFrame = pd.DataFrame(table_data["data"], columns=table_data["columns"])
        return pl.from_pandas(df)
    return None


def process_run_data(run_id: str, role: Literal["defuser", "expert"]) -> dict[str, Any]:
    """Process data from a single W&B run."""
    config_data: dict[str, Any] = format_config_data(load_run_config(run_id), role)
    summary_data: dict[str, Any] = format_summary_data(load_run_summary(run_id), role)

    run_data: dict[str, Any] = {**config_data, **summary_data, f"{role}_run_id": run_id}

    if role == "defuser":
        actions_df: pl.DataFrame | None = load_wandb_table(run_id, "actions")
        if actions_df is not None and not actions_df.is_empty():
            action_stats: dict[str, int] = process_actions_table(actions_df)
            run_data.update(action_stats)

    messages_df: pl.DataFrame | None = load_wandb_table(run_id, "messages")
    if messages_df is not None and not messages_df.is_empty():
        message_stats: dict[str, int | float] = process_messages_table(messages_df, role)
        run_data.update(message_stats)

    reflections_df: pl.DataFrame | None = load_wandb_table(run_id, "reflections")
    if reflections_df is not None and not reflections_df.is_empty():
        reflection: dict[str, str] = process_reflections_table(reflections_df, role)
        run_data.update(reflection)

    return run_data


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


def prepare_dataframe(dfs: dict[str, pl.DataFrame | None]) -> DataFrame | None:
    """Prepare and join dataframes from expert and defuser data."""
    expert_df: pl.DataFrame = (
        dfs["expert"].clone() if dfs["expert"] is not None else pl.DataFrame()
    )
    defuser_df: pl.DataFrame = (
        dfs["defuser"].clone() if dfs["defuser"] is not None else pl.DataFrame()
    )

    if not expert_df.is_empty():
        expert_df = rename_expert_columns(expert_df)

    if not defuser_df.is_empty():
        defuser_df = rename_defuser_columns(defuser_df)
        common_df: pl.DataFrame | None = create_common_dataframe(defuser_df)
        defuser_df = extract_defuser_metrics(defuser_df)
    else:
        return None

    try:
        if not defuser_df.is_empty() and common_df is not None:
            if not expert_df.is_empty():
                joined_df: pl.DataFrame = common_df.join(expert_df, on="game_id", how="inner")
                joined_df = joined_df.join(defuser_df, on="game_id", how="inner")
            else:
                joined_df = common_df.join(defuser_df, on="game_id", how="inner")

            joined_df = clean_joined_dataframe(joined_df)

            return joined_df
        st.warning("One or more dataframes are empty")
        return None  # noqa: TRY300
    except Exception as e:  # noqa: BLE001
        st.error(f"Error joining dataframes: {e!s}")
        st.exception(e)
        return None


def rename_expert_columns(expert_df: pl.DataFrame) -> DataFrame:
    """Rename columns in the expert dataframe for consistency."""
    rename_dict: dict[str, str] = {
        "total_expert_do_nothing_actions": "num_do_nothing_actions_expert",
        "total_expert_messages_sent": "num_messages_sent_expert",
        "total_guardrail_violations": "num_guardrail_violations_expert",
        "total_invalid_format": "num_invalid_format_expert",
        "total_prompt_truncations": "num_prompt_truncations_expert",
    }

    # Only include columns that exist
    rename_dict = {k: v for k, v in rename_dict.items() if k in expert_df.columns}

    if rename_dict:
        expert_df = expert_df.rename(rename_dict)

    # Add _expert suffix to remaining columns
    cols_to_suffix: list[str] = [
        col for col in expert_df.columns if not col.endswith("_expert") and col != "game_id"
    ]
    suffix_dict: dict[str, str] = {col: f"{col}_expert" for col in cols_to_suffix}

    if suffix_dict:
        expert_df = expert_df.rename(suffix_dict)

    return expert_df


def rename_defuser_columns(defuser_df: pl.DataFrame) -> DataFrame:
    """Rename columns in the defuser dataframe for consistency."""
    rename_dict: dict[str, str] = {
        "_runtime": "runtime",
        "step": "steps",
        "total_defuser_do_nothing_actions": "num_do_nothing_actions_defuser",
        "total_defuser_messages_sent": "num_messages_sent_defuser",
        "total_defuser_actions": "num_actions_defuser",
        "total_guardrail_violations": "num_guardrail_violations_defuser",
        "total_invalid_format": "num_invalid_format_defuser",
        "total_prompt_truncations": "prompt_truncations_defuser",
    }

    # Only include columns that exist
    rename_dict = {k: v for k, v in rename_dict.items() if k in defuser_df.columns}

    if rename_dict:
        defuser_df = defuser_df.rename(rename_dict)

    # Replace total_ prefix
    total_cols: list[str] = [col for col in defuser_df.columns if "total_" in col]
    rename_total_dict: dict[str, str] = {col: col.replace("total_", "") for col in total_cols}

    if rename_total_dict:
        defuser_df = defuser_df.rename(rename_total_dict)

    return defuser_df


def create_common_dataframe(defuser_df: pl.DataFrame) -> DataFrame | None:
    """Create a common dataframe with shared metadata."""
    common_cols_to_keep: list[str] = [
        "game_id",
        "condition",
        "communication_style",
        "thinking_framework",
        "include_manual",
        "is_playing_alone",
        "seed",
        "components",
        "num_widgets",
        "expert_name",
        "defuser_name",
        "steps",
        "runtime",
        "time_remaining",
        "is_solved",
        "is_strike_out",
        "is_timed_out",
        "modules_solved",
        "strikes",
    ]

    # Only include columns that exist
    common_cols_to_keep = [col for col in common_cols_to_keep if col in defuser_df.columns]

    if common_cols_to_keep:
        return defuser_df.select(common_cols_to_keep)
    return pl.DataFrame({"game_id": defuser_df["game_id"]})


def extract_defuser_metrics(defuser_df: pl.DataFrame) -> DataFrame:
    """Extract defuser-specific metrics."""
    defuser_cols: list[str] = ["game_id"]
    if "defuser_run_id" in defuser_df.columns:
        defuser_cols.append("defuser_run_id")

    standard_metrics: list[str] = [
        "num_do_nothing_actions_defuser",
        "num_messages_sent_defuser",
        "num_actions_defuser",
        "num_guardrail_violations_defuser",
        "num_invalid_format_defuser",
        "num_prompt_truncations_defuser",
    ]
    defuser_cols.extend([col for col in standard_metrics if col in defuser_df.columns])

    action_cols: list[str] = [col for col in defuser_df.columns if col.endswith("_action_count")]
    message_cols: list[str] = [
        col for col in defuser_df.columns if col.startswith("message_") and col.endswith("defuser")
    ]
    defuser_cols.extend(action_cols)
    defuser_cols.extend(message_cols)
    defuser_cols.append("reflection_defuser")

    if len(defuser_cols) > 1:
        return defuser_df.select(defuser_cols)
    return pl.DataFrame({"game_id": defuser_df["game_id"]})


def clean_joined_dataframe(joined_df: pl.DataFrame) -> DataFrame:
    """Clean and standardize the joined dataframe."""
    # Filter out rows with null expert or defuser names
    joined_df = joined_df.filter(
        pl.when(pl.col("is_playing_alone"))
        .then(pl.col("defuser_name").is_not_null())
        .otherwise(pl.col("expert_name").is_not_null() & pl.col("defuser_name").is_not_null())
    )

    # Convert boolean columns to integers
    bool_cols: list[str] = ["is_solved", "is_strike_out", "is_timed_out"]
    for col in bool_cols:
        if col in joined_df.columns:
            joined_df = joined_df.with_columns(pl.col(col).cast(pl.Int32).alias(col))

    # Convert float columns to integers where appropriate
    float_cols: list[str] = [
        col
        for col in joined_df.columns
        if (joined_df[col].dtype == pl.Float64 or joined_df[col].dtype == pl.Float32)
    ]

    for col in float_cols:
        joined_df = joined_df.with_columns(pl.col(col).fill_null(0).cast(pl.Int32).alias(col))

    # Fill nulls in action count columns
    for col in joined_df.columns:
        if col.endswith("_action_count"):
            joined_df = joined_df.with_columns(pl.col(col).fill_null(0).cast(pl.Int32).alias(col))

    # Round message length columns
    for col in joined_df.columns:
        if col.startswith("message_"):
            joined_df = joined_df.with_columns(
                pl.col(col).fill_null(0).cast(pl.Float64).round(2).alias(col)
            )

    return joined_df


def process_role_data(role: str, role_idx: int, progress_bar: Any, status_text: Any) -> DataFrame:
    """Process data for a specific role (expert or defuser)."""
    runs_data: list[dict[str, Any]] = []
    total_runs: int = len(st.session_state.valid_run_ids)
    for run_idx, run_id in enumerate(st.session_state.valid_run_ids):
        progress: float = (role_idx * total_runs + run_idx) / (2 * total_runs)
        progress_bar.progress(progress)

        run_config: dict[str, Any] = load_run_config(run_id)
        game_id: Any = run_config.get("game_id")
        status_text.text(f"Processing {role} run {run_idx + 1}/{total_runs} (game {game_id})")

        run_data: dict[str, Any] = process_run_data(run_id, role)
        runs_data.append(run_data)

    return pl.DataFrame(runs_data)


def load_run_config(run_id: str) -> dict[str, Any]:
    """Load the configuration for a specific run."""
    config_path: Path = Path(f"wandb/runs/run-{run_id}/config.json")
    if config_path.exists():
        with config_path.open() as f:
            return json.load(f)
    return {}


def load_run_summary(run_id: str) -> dict[str, Any]:
    """Load the summary for a specific run."""
    summary_path: Path = Path(f"wandb/runs/run-{run_id}/summary.json")
    if summary_path.exists():
        with summary_path.open() as f:
            return json.load(f)
    return {}


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


def is_relevant_run(run_id: str, role: str) -> bool:
    """Check if a run matches the given experiment criteria."""
    run_config: dict[str, Any] = load_run_config(run_id)
    if not run_config:
        return False

    if "role" not in run_config or run_config["role"] != role:
        return False

    for criterion in st.session_state.experiment_criteria:
        for key, value in criterion.items():
            if isinstance(value, dict) and "$in" in value:
                if run_config.get(key.replace("config.", "")) not in value["$in"]:
                    return False
            elif run_config.get(key.replace("config.", "")) != value:
                return False
    return True


def maybe_fetch_runs_from_wandb(role: str) -> bool:
    existing_run_ids: list[str] = get_existing_runs_from_local_dir()
    relevant_run_ids: list[str] = [
        run_id for run_id in existing_run_ids if is_relevant_run(run_id, role)
    ]
    valid_run_ids: list[str] = [run_id for run_id in relevant_run_ids if has_all_data(run_id)]

    st.session_state.valid_run_ids = valid_run_ids

    runs: Runs | None = fetch_runs(role, valid_run_ids)
    if runs and len(runs):
        for run in runs:
            dump_run_data(run)
            download_artifacts(run)
        return True

    if not valid_run_ids and not runs:
        st.warning(f"No runs found for {role}. Please check your criteria or try again later.")

    return False


def load_and_process_run_data() -> DataFrame | None:
    """Load and process data from Weights & Biases."""
    with st.spinner("Loading and processing data..."):
        status_text = st.empty()
        progress_bar = st.progress(0)

        dfs: dict[str, pl.DataFrame | None] = {"expert": None, "defuser": None}

        roles_to_process: list[str] = (
            ["defuser"] if st.session_state.get("playing_alone", False) else ["expert", "defuser"]
        )

        for role_idx, role in enumerate(roles_to_process):
            status_text.text(f"Collating data for {role} runs...")

            unchecked_runs: bool = True
            while unchecked_runs:
                unchecked_runs = maybe_fetch_runs_from_wandb(role)

            dfs[role] = process_role_data(role, role_idx, progress_bar, status_text)

        status_text.text("Processing dataframes...")

        for df_name in ["expert", "defuser"]:
            if df_name in dfs and dfs[df_name] is not None and "game_id" in dfs[df_name].columns:
                dfs[df_name] = dfs[df_name].sort("game_id")

        joined_df: DataFrame | None = prepare_dataframe(dfs)

        status_text.empty()
        progress_bar.empty()

        return joined_df


def create_aggregate_expressions(
    aggregate_metrics_by: list[str], agg_functions: list[str]
) -> list[Any]:
    """Create polars expressions for aggregation."""
    agg_exprs: list[Any] = []
    for metric in aggregate_metrics_by:
        for func in agg_functions:
            if func == "mean":
                agg_exprs.append(pl.mean(metric).alias(f"{metric}_{func}"))
            elif func == "median":
                agg_exprs.append(pl.median(metric).alias(f"{metric}_{func}"))
            elif func == "min":
                agg_exprs.append(pl.min(metric).alias(f"{metric}_{func}"))
            elif func == "max":
                agg_exprs.append(pl.max(metric).alias(f"{metric}_{func}"))
            elif func == "count":
                agg_exprs.append(pl.count(metric).alias(f"{metric}_{func}"))
            elif func == "sum":
                agg_exprs.append(pl.sum(metric).alias(f"{metric}_{func}"))
    return agg_exprs


def perform_aggregation(
    df: pl.DataFrame,
    groupby_cols: list[str],
    aggregate_metrics_by: list[str],
    agg_functions: list[str],
) -> DataFrame:
    """Perform aggregation on the dataframe."""
    agg_exprs: list[Any] = create_aggregate_expressions(aggregate_metrics_by, agg_functions)
    aggregated_df: pl.DataFrame = df.group_by(groupby_cols).agg(agg_exprs)

    # Round floating point columns
    for col in aggregated_df.columns:
        if col not in groupby_cols:
            col_dtype = aggregated_df[col].dtype
            if str(col_dtype).startswith(("f32", "f64", "decimal")):
                aggregated_df = aggregated_df.with_columns(pl.col(col).round(2).alias(col))

    return aggregated_df


def create_visualizations(
    df: pl.DataFrame, aggregate_metrics_by: list[str], groupby_cols: list[str]
) -> None:
    """Create visualizations for the aggregated data."""
    for metric in aggregate_metrics_by:
        st.subheader(f"Visualization for {metric}")

        if len(groupby_cols) == 1:
            try:
                chart_data: pd.DataFrame = (
                    df.group_by(groupby_cols[0]).agg(pl.mean(metric).alias(metric)).to_pandas()
                )
                st.bar_chart(chart_data.set_index(groupby_cols[0]))
            except Exception as e:  # noqa: BLE001
                st.warning(f"Could not create bar chart: {e}")

        elif len(groupby_cols) == 2 and "mean" == "mean":  # Always include mean
            try:
                pivot_data: pd.DataFrame = (
                    df.select([*groupby_cols, metric])
                    .to_pandas()
                    .pivot_table(
                        values=metric,
                        index=groupby_cols[0],
                        columns=groupby_cols[1],
                        aggfunc="mean",
                    )
                )
                st.write(f"Average {metric} by {groupby_cols[0]} and {groupby_cols[1]}")
                st.dataframe(pivot_data)
            except Exception as e:  # noqa: BLE001
                st.warning(f"Could not create pivot table: {e}")


def get_numeric_columns(df: pl.DataFrame) -> list[str]:
    """Extract numeric columns from the dataframe."""
    try:
        numeric_cols: list[str] = []
        for col in df.columns:
            dtype = df[col].dtype
            if (
                dtype
                in [
                    pl.Int8,
                    pl.Int16,
                    pl.Int32,
                    pl.Int64,
                    pl.Float32,
                    pl.Float64,
                    pl.UInt8,
                    pl.UInt16,
                    pl.UInt32,
                    pl.UInt64,
                ]
                and col != "seed"
            ):
                numeric_cols.append(col)

        # Add action and message columns
        action_message_cols: list[str] = [
            col
            for col in df.columns
            if (col.endswith("_action_count"))
            or (
                col.startswith("message_")
                and any(
                    x in col for x in ["length_sum", "length_mean", "length_min", "length_max"]
                )
            )
        ]

        for col in action_message_cols:
            if col not in numeric_cols and col != "seed" and col in df.columns:
                numeric_cols.append(col)

        return sorted(numeric_cols)
    except Exception as e:  # noqa: BLE001
        st.sidebar.error(f"Error getting numeric columns: {e!s}")
        if "debug_mode" in st.session_state and st.session_state.debug_mode:
            st.exception(e)
        return []


def transform_to_model_based(df: pl.DataFrame) -> pl.DataFrame:
    """Transform dataframe to model-based format."""
    expert_data: pl.DataFrame = df.clone()
    expert_data = expert_data.with_columns(
        [pl.col("expert_name").alias("model"), pl.lit("expert").alias("role")]
    )

    defuser_data: pl.DataFrame = df.clone()
    defuser_data = defuser_data.with_columns(
        [pl.col("defuser_name").alias("model"), pl.lit("defuser").alias("role")]
    )

    return pl.concat([expert_data, defuser_data])


def add_partial_success_column(df: pl.DataFrame) -> pl.DataFrame:
    """Add a column indicating partial success based on solved modules."""
    if "modules_solved" in df.columns and "components" in df.columns:
        df = df.with_columns(
            (pl.col("modules_solved") / pl.col("components").list.len()).alias("partial_success")
        )
    return df


def add_component_analysis_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Add component analysis columns to the dataframe."""
    if "components" in df.columns:
        sample_row: pl.DataFrame = df.filter(pl.col("components").is_not_null()).head(1)
        if len(sample_row) > 0:
            sample_components: Any = sample_row[0, "components"]

            if isinstance(sample_components, list):
                df = df.with_columns(pl.col("components").list.first().alias("component_type"))
                df = df.with_columns(pl.col("components").list.len().alias("num_components"))

    return df


def determine_outcome(df: pl.DataFrame) -> pl.DataFrame:
    """Determine the outcome of each run."""
    if all(col in df.columns for col in ["is_solved", "is_strike_out", "is_timed_out"]):
        df = df.with_columns(pl.lit("unknown").alias("outcome"))

        df = df.with_columns(
            pl.when(pl.col("is_solved") == 1)
            .then(pl.lit("solved"))
            .when(pl.col("is_strike_out") == 1)
            .then(pl.lit("strike out"))
            .when(pl.col("is_timed_out") == 1)
            .then(pl.lit("timed out"))
            .otherwise(pl.col("outcome"))
            .alias("outcome")
        )

        if all(col in df.columns for col in ["modules_solved", "components", "strikes"]):
            df = df.with_columns(
                pl.when(pl.col("outcome") == "unknown")
                .then(
                    pl.when(
                        pl.col("modules_solved").is_not_null()
                        & pl.col("components").is_not_null()
                        & (pl.col("modules_solved") == pl.col("components").list.len())
                    )
                    .then(pl.lit("solved"))
                    .when(pl.col("strikes") == 3)
                    .then(pl.lit("strike out"))
                    .otherwise(pl.lit("timed out"))
                )
                .otherwise(pl.col("outcome"))
                .alias("outcome")
            )

    return df


def add_pairing_columns(
    df: pl.DataFrame, best_expert: str | None, best_defuser: str | None
) -> pl.DataFrame:
    """Add columns to identify different types of model pairings."""
    df = df.with_columns(
        [pl.lit(best_expert).alias("best_expert"), pl.lit(best_defuser).alias("best_defuser")]
    )

    df = df.with_columns(
        [
            (pl.col("expert_name") == pl.col("defuser_name")).alias("with_same"),
            (pl.col("expert_name") == pl.col("best_expert")).alias("with_best_expert"),
            (pl.col("defuser_name") == pl.col("best_defuser")).alias("with_best_defuser"),
        ]
    )

    df = df.with_columns(
        (~(pl.col("with_same") | pl.col("with_best_expert") | pl.col("with_best_defuser"))).alias(
            "with_rest"
        )
    )

    return df


def find_best_models(df: pl.DataFrame, experiment: int | None) -> tuple[str | None, str | None]:
    """Find the best expert and defuser models based on solved count."""
    if experiment == 1:
        if len(df.select("expert_name").unique().to_series()) > 0:
            grouped_expert: pl.DataFrame = df.group_by("expert_name").agg(
                pl.sum("is_solved").alias("solved_count")
            )
            grouped_expert = grouped_expert.sort("solved_count", descending=True)
            best_expert: str = grouped_expert.row(0)[0]

            if "debug_mode" in st.session_state and st.session_state.debug_mode:
                st.sidebar.text(f"Best Expert: {best_expert}")
        else:
            best_expert = None

        if len(df.select("defuser_name").unique().to_series()) > 0:
            grouped_defuser: pl.DataFrame = df.group_by("defuser_name").agg(
                pl.sum("is_solved").alias("solved_count")
            )
            grouped_defuser = grouped_defuser.sort("solved_count", descending=True)
            best_defuser: str = grouped_defuser.row(0)[0]

            if "debug_mode" in st.session_state and st.session_state.debug_mode:
                st.sidebar.text(f"Best Defuser: {best_defuser}")
        else:
            best_defuser = None
    else:
        expert_options: list[str] = (
            df.select("expert_name").unique().to_series().drop_nulls().to_list()
        )
        defuser_options: list[str] = (
            df.select("defuser_name").unique().to_series().drop_nulls().to_list()
        )

        # Initialize session state for best models
        if "best_expert_model" not in st.session_state:
            st.session_state.best_expert_model = expert_options[0] if expert_options else None

        # We skip the best defuser selection for analyses of runs without expert
        if st.session_state.best_expert_model is not None:
            if "best_defuser_model" not in st.session_state:
                st.session_state.best_defuser_model = (
                    defuser_options[0] if defuser_options else None
                )

            best_expert = st.sidebar.selectbox(
                "Best 'Expert' model",
                expert_options,
                index=expert_options.index(st.session_state.best_expert_model)
                if st.session_state.best_expert_model in expert_options
                else 0,
            )

            # Update session state
            st.session_state.best_expert_model = best_expert

            if not best_expert:
                st.warning("Please select a best expert model")
                return None, None

            best_defuser = st.sidebar.selectbox(
                "Best 'Defuser' model",
                defuser_options,
                index=defuser_options.index(st.session_state.best_defuser_model)
                if st.session_state.best_defuser_model in defuser_options
                else 0,
            )

            # Update session state
            st.session_state.best_defuser_model = best_defuser

            if not best_defuser:
                st.warning("Please select a best defuser model")
                return None, None

        else:
            st.session_state.best_defuser_model = None

    return st.session_state.best_expert_model, st.session_state.best_defuser_model


def apply_pairing_filters(
    df: pl.DataFrame,
    filter_same: bool,
    filter_best_expert: bool,
    filter_best_defuser: bool,
    filter_rest: bool,
) -> pl.DataFrame:
    """Apply filters based on model pairings."""
    if filter_same:
        df = df.filter(pl.col("with_same"))
    if filter_best_expert:
        df = df.filter(pl.col("with_best_expert"))
    if filter_best_defuser:
        df = df.filter(pl.col("with_best_defuser"))
    if filter_rest:
        df = df.filter(pl.col("with_rest"))

    return df


def setup_debug_mode() -> bool:
    """Setup debug mode and display version information."""
    # Initialize session state for debug mode
    if "debug_mode" not in st.session_state:
        st.session_state.debug_mode = False

    debug_mode: bool = st.sidebar.checkbox("Debug Mode", value=st.session_state.debug_mode)
    st.session_state.debug_mode = debug_mode

    if debug_mode:
        st.sidebar.text(f"Streamlit version: {st.__version__}")
        st.sidebar.text(f"Polars version: {pl.__version__}")

    return debug_mode


def select_filtering_method() -> str:
    """Select between predefined experiment or custom criteria."""
    st.sidebar.subheader("Select Data Filtering Method")

    # Initialize session state if not present
    if "filter_method" not in st.session_state:
        st.session_state.filter_method = "Predefined Experiment"

    filter_method: str = st.sidebar.radio(
        "Filter Method",
        ["Predefined Experiment", "Custom Criteria"],
        index=0 if st.session_state.filter_method == "Predefined Experiment" else 1,
    )

    # Update session state
    st.session_state.filter_method = filter_method

    return filter_method


def handle_predefined_experiment() -> tuple[int | None, bool]:
    """Handle selection of predefined experiment."""
    st.sidebar.subheader("Select Experiment")

    if "previous_experiment" not in st.session_state:
        st.session_state.previous_experiment = None

    # Use session state to maintain selection
    experiment: int | None = st.sidebar.selectbox(
        "Experiment #",
        list(range(1, 8)),
        index=st.session_state.previous_experiment - 1
        if st.session_state.previous_experiment
        else None,
    )

    criteria_changed: bool = False
    if experiment != st.session_state.previous_experiment:
        criteria_changed = True
        st.session_state.previous_experiment = experiment
        st.session_state.results_data_loaded = False
        st.session_state.df = None

    if not experiment:
        st.info("Please select an experiment number")
        return None, criteria_changed

    st.session_state.experiment_criteria = get_experiment_criteria(experiment)
    return experiment, criteria_changed


def handle_custom_criteria() -> tuple[None, bool]:
    """Handle selection of custom criteria."""
    st.sidebar.subheader("Select Custom Criteria")

    if "previous_custom_criteria" not in st.session_state:
        st.session_state.previous_custom_criteria = None

    experiment_criteria: list[dict[str, Any]] = get_custom_criteria()
    st.session_state.experiment_criteria = experiment_criteria

    criteria_json: str = json.dumps(experiment_criteria, sort_keys=True)

    criteria_changed: bool = False
    if criteria_json != st.session_state.previous_custom_criteria:
        criteria_changed = True
        st.session_state.previous_custom_criteria = criteria_json
        st.session_state.results_data_loaded = False
        st.session_state.df = None

    return None, criteria_changed


def display_debug_criteria() -> None:
    """Display debug information about the criteria."""
    st.sidebar.subheader("Debug: W&B Query Criteria")

    formatted_criteria: list[str] = []
    for criterion in st.session_state.experiment_criteria:
        for key, value in criterion.items():
            if isinstance(value, dict) and "$in" in value:
                formatted_criteria.append(f"{key} in {value['$in']}")
            else:
                formatted_criteria.append(f"{key} = {value}")

    for criterion in formatted_criteria:
        st.sidebar.text(criterion)

    if (
        st.session_state.filter_method == "Custom Criteria"
        and "debug_selections" in st.session_state
    ):
        st.sidebar.subheader("Debug: User Selections")
        for key, value in st.session_state.debug_selections.items():
            if value is not None:
                st.sidebar.text(f"{key}: {value}")


def fetch_and_process_data(criteria_changed: bool, debug_mode: bool) -> bool:
    """Fetch and process data based on criteria."""
    fetch_button: bool = st.sidebar.button("Fetch runs!")

    if not fetch_button and not criteria_changed:
        return False

    if criteria_changed and not fetch_button:
        st.info("Criteria have changed. Please click 'Fetch runs!' to update the data.")
        return False

    st.session_state.results_data_loaded = False
    st.session_state.df = None

    result: DataFrame | None = load_and_process_run_data()

    if result is None:
        st.error("Failed to load or process data")
        return False

    df: DataFrame = result

    if df is not None and not df.is_empty():
        st.session_state.df = df
        st.session_state.results_data_loaded = True
        st.success("Data loaded and processed successfully!")

        csv: str = df.to_pandas().to_csv()
        st.download_button(
            label="Download full dataset as CSV",
            data=csv,
            file_name="full_dataset.csv",
            mime="text/csv",
        )

        if debug_mode:
            st.write("DataFrame schema:")
            st.text(df.schema)

            st.write("DataFrame head:")
            st.dataframe(df.head())

            st.write("DataFrame columns:")
            st.write(df.columns)

        return True
    st.error("Failed to load or process data")
    return False


def prepare_dataframe_for_analysis(
    df: pl.DataFrame, experiment: int | None, debug_mode: bool
) -> tuple[pl.DataFrame | None, str | None, str | None]:
    """Prepare the dataframe for analysis by adding columns and determining outcomes."""
    # Calculate the partial success column
    df = add_partial_success_column(df)

    # Find best models
    best_expert, best_defuser = find_best_models(df, experiment)
    if (best_expert is None or best_defuser is None) and not st.session_state.get(
        "playing_alone", False
    ):
        return None, None, None

    # Add pairing columns
    df = add_pairing_columns(df, best_expert, best_defuser)

    # Determine outcome
    df = determine_outcome(df)

    if debug_mode and "outcome" in df.columns:
        outcome_counts: pl.DataFrame = (
            df.group_by("outcome").count().sort("count", descending=True)
        )
        st.sidebar.write("Outcome distribution:", outcome_counts.to_pandas())

        if "unknown" in df["outcome"].unique():
            st.sidebar.warning(
                f"There are still {df.filter(pl.col('outcome') == 'unknown').height} unknown outcomes"
            )
        else:
            st.sidebar.success("All outcomes were successfully determined")

    return df, best_expert, best_defuser


def prepare_numeric_columns(
    df: pl.DataFrame, debug_mode: bool
) -> tuple[pl.DataFrame, list[str] | None]:
    """Prepare numeric columns for aggregation."""
    if "numeric_cols" not in st.session_state:
        try:
            # Convert action and message columns to appropriate types
            for col in df.columns:
                if (col.endswith("_action_count")) or (
                    col.startswith("message_")
                    and any(
                        x in col for x in ["length_sum", "length_mean", "length_min", "length_max"]
                    )
                ):
                    try:
                        if "count" in col:
                            df = df.with_columns(
                                pl.col(col).fill_null(0).cast(pl.Int32).alias(col)
                            )
                        else:
                            df = df.with_columns(
                                pl.col(col).fill_null(0).cast(pl.Float64).round(2).alias(col)
                            )
                    except Exception as e:  # noqa: BLE001
                        if debug_mode:
                            st.sidebar.warning(f"Could not convert {col} to numeric: {e}")

            st.session_state.df = df
            st.session_state.numeric_cols = get_numeric_columns(df)

        except Exception as e:  # noqa: BLE001
            st.sidebar.error(f"Error getting numeric columns: {e!s}")
            if debug_mode:
                st.exception(e)
            return df, None

    numeric_cols: list[str] = st.session_state.numeric_cols

    if not numeric_cols:
        st.warning("No numeric columns found in the data")
        return df, None

    return df, numeric_cols


def setup_aggregation_options(numeric_cols: list[str]) -> tuple[list[str], bool]:
    """Set up aggregation options in the sidebar."""
    st.sidebar.subheader("Select Metrics and Aggregation Options")

    # Initialize session state for metrics if not present
    if "aggregate_metrics_selection" not in st.session_state:
        st.session_state.aggregate_metrics_selection = []

    # Use session state to maintain selection
    aggregate_metrics_by: list[str] = st.sidebar.multiselect(
        "Select metrics to aggregate",
        numeric_cols,
        default=st.session_state.aggregate_metrics_selection,
    )

    # Update session state with current selection
    st.session_state.aggregate_metrics_selection = aggregate_metrics_by

    if not aggregate_metrics_by:
        st.sidebar.info("Please select at least one metric to aggregate")

    # Initialize session state for model-based analysis if not present
    if "create_model_column" not in st.session_state:
        st.session_state.create_model_column = False

    # Use session state to maintain checkbox state
    create_model_column: bool = st.sidebar.checkbox(
        "Enable model-based analysis", value=st.session_state.create_model_column
    )

    # Update session state with current checkbox state
    st.session_state.create_model_column = create_model_column

    return aggregate_metrics_by, create_model_column


def get_groupby_options(
    df: pl.DataFrame, create_model_column: bool
) -> tuple[pl.DataFrame, list[str] | None, list[str] | None]:
    """Get groupby options based on dataframe columns and model-based analysis."""
    base_groupby_options: list[str] = [
        "condition",
        "communication_style",
        "thinking_framework",
        "is_playing_alone",
        "include_manual",
        "seed",
        "game_id",
        "num_widgets",
        "outcome",
        "reflection_defuser",
        "reflection_expert",
    ]

    if create_model_column:
        groupby_options: list[str] = ["model", "role", *base_groupby_options]
    else:
        groupby_options = ["expert_name", "defuser_name", *base_groupby_options]

    # Add component analysis options
    df = add_component_analysis_columns(df)
    if "component_type" in df.columns:
        groupby_options.append("component_type")
    if "num_components" in df.columns:
        groupby_options.append("num_components")

    if "components" in df.columns:
        groupby_options.append("components")

        # Initialize session state for explode_components
        if "explode_components" not in st.session_state:
            st.session_state.explode_components = False

        explode_components: bool = st.sidebar.checkbox(
            "Explode Components for Analysis", value=st.session_state.explode_components
        )

        # Update session state
        st.session_state.explode_components = explode_components

        if explode_components:
            df = df.explode("components")
            st.info("Components have been exploded. Each row now represents a single component.")

    available_groupby: list[str] = sorted([col for col in groupby_options if col in df.columns])

    if not available_groupby:
        st.warning("No groupby columns available")
        return df, None, None

    # Initialize session state for groupby_cols
    if "groupby_cols" not in st.session_state:
        st.session_state.groupby_cols = [available_groupby[0]] if available_groupby else []

    # Use available_groupby to filter any stale selections in session state
    valid_selections: list[str] = sorted(
        [col for col in st.session_state.groupby_cols if col in available_groupby]
    )

    groupby_cols: list[str] = st.sidebar.multiselect(
        "Group by", available_groupby, default=valid_selections
    )

    # Update session state
    st.session_state.groupby_cols = groupby_cols

    # Initialize session state for agg_functions
    if "agg_functions" not in st.session_state:
        st.session_state.agg_functions = ["mean", "count"]

    agg_functions: list[str] = st.sidebar.multiselect(
        "Aggregation functions",
        ["mean", "median", "min", "max", "count", "sum"],
        default=st.session_state.agg_functions,
    )

    # Update session state
    st.session_state.agg_functions = agg_functions

    return df, groupby_cols, agg_functions


def setup_pairing_filters(
    groupby_cols: list[str], best_expert: str | None, best_defuser: str | None
) -> tuple[bool, bool, bool, bool]:
    """Set up pairing filters in the sidebar."""
    st.sidebar.subheader("Pairing Filters")

    # Initialize session state for filters
    if "filter_same" not in st.session_state:
        st.session_state.filter_same = False
    if "filter_best_expert" not in st.session_state:
        st.session_state.filter_best_expert = False
    if "filter_best_defuser" not in st.session_state:
        st.session_state.filter_best_defuser = False
    if "filter_rest" not in st.session_state:
        st.session_state.filter_rest = False

    filter_same: bool = st.sidebar.checkbox(
        "Pairings where Expert = Defuser", value=st.session_state.filter_same
    )
    st.session_state.filter_same = filter_same

    # Configure pairing filters
    filter_best_expert: bool = False
    filter_best_defuser: bool = False

    if groupby_cols:
        if "defuser_name" in groupby_cols and "expert_name" not in groupby_cols:
            filter_best_expert = st.sidebar.checkbox(
                f"Pairings with best expert ({best_expert})",
                value=st.session_state.filter_best_expert,
            )
            st.session_state.filter_best_expert = filter_best_expert
        elif "expert_name" in groupby_cols and "defuser_name" not in groupby_cols:
            filter_best_defuser = st.sidebar.checkbox(
                f"Pairings with best defuser ({best_defuser})",
                value=st.session_state.filter_best_defuser,
            )
            st.session_state.filter_best_defuser = filter_best_defuser
        else:
            filter_best_expert = st.sidebar.checkbox(
                f"Pairings with best expert ({best_expert})",
                value=st.session_state.filter_best_expert,
            )
            st.session_state.filter_best_expert = filter_best_expert

            filter_best_defuser = st.sidebar.checkbox(
                f"Pairings with best defuser ({best_defuser})",
                value=st.session_state.filter_best_defuser,
            )
            st.session_state.filter_best_defuser = filter_best_defuser

    filter_rest: bool = st.sidebar.checkbox("Other pairings", value=st.session_state.filter_rest)
    st.session_state.filter_rest = filter_rest

    return filter_same, filter_best_expert, filter_best_defuser, filter_rest


def apply_outcome_filter(df: pl.DataFrame) -> pl.DataFrame:
    """Apply outcome filter if available."""
    if "outcome" not in df.columns:
        return df

    st.sidebar.subheader("Outcome Filter")

    unique_outcomes: list[str] = sorted(df["outcome"].unique().to_list())

    # Initialize session state for selected outcomes
    if "selected_outcomes" not in st.session_state:
        st.session_state.selected_outcomes = unique_outcomes

    # Filter out any outcomes that no longer exist in the data
    valid_selections: list[str] = [
        outcome for outcome in st.session_state.selected_outcomes if outcome in unique_outcomes
    ]

    selected_outcomes: list[str] = st.sidebar.multiselect(
        "Filter by outcomes", options=unique_outcomes, default=valid_selections
    )

    # Update session state
    st.session_state.selected_outcomes = selected_outcomes

    if selected_outcomes and len(selected_outcomes) < len(unique_outcomes):
        df = df.filter(pl.col("outcome").is_in(selected_outcomes))
        st.sidebar.info(f"Showing {len(df)} runs with outcomes: {', '.join(selected_outcomes)}")

    return df


def display_visualizations_for_aggregation(
    df: pl.DataFrame, aggregate_metrics_by: list[str], groupby_cols: list[str]
) -> None:
    """Display visualizations for aggregated data."""
    # Empty function for now


def setup_visualization_viewer() -> bool:
    """Setup visualization viewer controls."""
    if st.session_state.get("aggregation_performed", False):
        # Initialize session state for show_visualizations
        if "show_visualizations" not in st.session_state:
            st.session_state.show_visualizations = False

        st.sidebar.subheader("Enable visualisations")

        show_visualizations: bool = st.sidebar.checkbox(
            "Show visualizations", value=st.session_state.show_visualizations
        )

        # Update session state
        st.session_state.show_visualizations = show_visualizations

        if show_visualizations and st.sidebar.button("Generate Visualizations"):
            # Set flag to show visualizations instead of calling display function directly
            st.session_state.show_visualizations_for_data = True

        return show_visualizations
    return False


def perform_and_display_aggregation(
    df: pl.DataFrame,
    groupby_cols: list[str],
    aggregate_metrics_by: list[str],
    agg_functions: list[str],
) -> pl.DataFrame | None:
    """Perform aggregation and display results."""
    # Use a unique key for this button to avoid conflicts
    confirm_aggregate: bool = st.sidebar.button("Aggregate!", key="confirm_aggregate_button")

    # Store aggregation state in session
    if "aggregation_performed" not in st.session_state:
        st.session_state.aggregation_performed = False

    # Update aggregation state if button is pressed
    if confirm_aggregate:
        st.session_state.aggregation_performed = True

    # Check if we should perform aggregation
    should_aggregate: bool = (
        st.session_state.aggregation_performed
        and aggregate_metrics_by
        and groupby_cols
        and agg_functions
    )

    if not should_aggregate:
        if not aggregate_metrics_by or not groupby_cols or not agg_functions:
            st.sidebar.warning(
                "Please select metrics, group by columns, and aggregation functions"
            )
        return None

    st.subheader("Aggregation Results")

    aggregated_df: pl.DataFrame = perform_aggregation(
        df, groupby_cols, aggregate_metrics_by, agg_functions
    )

    if aggregated_df is None:
        return None

    st.dataframe(aggregated_df)

    csv: str = aggregated_df.to_pandas().to_csv()
    st.download_button(
        label="Download aggregated data as CSV",
        data=csv,
        file_name="aggregated_results.csv",
        mime="text/csv",
    )

    return aggregated_df  # Return the aggregated dataframe for visualizations


def main() -> None:
    """Main function for the GPTNT Results Visualizer."""
    # Setup debug mode
    maybe_clear_session_state()
    debug_mode: bool = setup_debug_mode()

    # Select filtering method
    filter_method: str = select_filtering_method()

    # Get experiment criteria based on filtering method
    if st.session_state.filter_method == "Predefined Experiment":
        experiment, criteria_changed = handle_predefined_experiment()
    else:
        experiment, criteria_changed = handle_custom_criteria()

    if not st.session_state.get("experiment_criteria", False):
        st.warning("No criteria selected")
        return

    # Display debug information if needed
    if debug_mode:
        display_debug_criteria()

    # Check if data is already loaded or needs to be loaded
    if not st.session_state.get("results_data_loaded", False):
        results_data_loaded: bool = fetch_and_process_data(criteria_changed, debug_mode)
        if not results_data_loaded:
            st.info("Please fetch data first using the 'Fetch runs!' button in the sidebar.")
            return

    # Work with the loaded data
    if (
        st.session_state.get("results_data_loaded", False)
        and st.session_state.get("df") is not None
    ):
        df: pl.DataFrame = st.session_state.df

        main_content = st.container()
        with main_content:
            header_placeholder = st.empty()
            header_placeholder.header("Runs have been fetched!")

        # Check if we're in a scenario where we don't need expert-defuser pairing analysis
        is_experiment_3: bool = experiment == 3
        is_only_alone: bool = filter_method == "Custom Criteria" and st.session_state.get(
            "defuser_playing"
        ) == ["Alone"]
        skip_pairing_analysis: bool = is_experiment_3 or is_only_alone

        # Prepare dataframe for analysis
        if skip_pairing_analysis:
            # For Experiment 3 or "Alone" only scenarios, skip best model finding
            df = add_partial_success_column(df)
            df = determine_outcome(df)
            best_expert, best_defuser = None, None

            if debug_mode and "outcome" in df.columns:
                outcome_counts: pl.DataFrame = (
                    df.group_by("outcome").count().sort("count", descending=True)
                )
                st.sidebar.write("Outcome distribution:", outcome_counts.to_pandas())
        else:
            # Normal case with expert-defuser pairings
            df, best_expert, best_defuser = prepare_dataframe_for_analysis(
                df, experiment, debug_mode
            )
            if df is None:
                return

        # Prepare numeric columns
        df, numeric_cols = prepare_numeric_columns(df, debug_mode)
        if numeric_cols is None:
            return

        # Setup aggregation options
        aggregate_metrics_by, create_model_column = setup_aggregation_options(numeric_cols)

        # Transform to model-based format if requested
        if create_model_column:
            df = transform_to_model_based(df)
            st.info(
                "Data transformed to model-based format. Each row now represents a model in a specific role."
            )

        # Get groupby options
        df, groupby_cols, agg_functions = get_groupby_options(df, create_model_column)
        if groupby_cols is None:
            return

        # Setup pairing filters ONLY when we have expert-defuser pairings
        if not skip_pairing_analysis and best_expert is not None and best_defuser is not None:
            filter_same, filter_best_expert, filter_best_defuser, filter_rest = (
                setup_pairing_filters(groupby_cols, best_expert, best_defuser)
            )

            # Apply pairing filters
            df = apply_pairing_filters(
                df, filter_same, filter_best_expert, filter_best_defuser, filter_rest
            )

            if filter_same or filter_best_expert or filter_best_defuser or filter_rest:
                st.sidebar.info(f"Showing {len(df)} runs after applying filters.")

        # Apply outcome filter
        df = apply_outcome_filter(df)

        # Perform and display aggregation
        perform_and_display_aggregation(df, groupby_cols, aggregate_metrics_by, agg_functions)

        # Setup visualization viewer controls
        show_visualization_viewer: bool = setup_visualization_viewer()

        # Show visualizations if requested
        if show_visualization_viewer and st.session_state.get("show_visualizations_for_data"):
            st.write("---")  # Add separator
            display_visualizations_for_aggregation(df, aggregate_metrics_by, groupby_cols)

            # Add button to close visualization viewer
            if st.button("Close Visualization Viewer"):
                del st.session_state.show_visualizations_for_data
                st.rerun()


if __name__ == "__main__":
    main()
