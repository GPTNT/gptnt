import functools
import hashlib
import json
import pickle
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import polars as pl
import streamlit as st
import structlog
import wandb

# Set page configuration for better performance
st.set_page_config(
    page_title="GPTNT Results Visualizer", layout="wide", initial_sidebar_state="expanded"
)

# Initialize session state
if "data_loaded" not in st.session_state:
    st.session_state.data_loaded = False
if "df" not in st.session_state:
    st.session_state.df = None
if "aggregate_metrics" not in st.session_state:
    st.session_state.aggregate_metrics = []

wandb_entity = wandb.env.get_entity() or "gptnt"
wandb_project = "for-real"

wandb_api = wandb.Api()

logger = structlog.get_logger()

CACHE_DIR = ".cache"


def disk_memoize(cache_dir: str = CACHE_DIR, max_age_seconds: int | None = None):
    Path(cache_dir).mkdir(exist_ok=True)

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Generate unique cache key
            hash_input = (func.__name__, args, frozenset(kwargs.items()))
            hash_str = hashlib.md5(pickle.dumps(hash_input)).hexdigest()
            cache_path = Path(cache_dir) / f"{func.__name__}_{hash_str}.pkl"

            # Try to load from cache
            if cache_path.exists():
                with open(cache_path, "rb") as f:
                    cache_data = pickle.load(f)
                    cached_time = cache_data["timestamp"]
                    result = cache_data["result"]

                    if (
                        max_age_seconds is None
                        or (datetime.now() - cached_time).total_seconds() <= max_age_seconds
                    ):
                        return result  # valid cache

            # Compute and save to cache
            result = func(*args, **kwargs)
            cache_data = {"timestamp": datetime.now(), "result": result}
            with open(cache_path, "wb") as f:
                pickle.dump(cache_data, f)

            return result

        return wrapper

    return decorator


def get_custom_criteria():
    """Allow users to select individual criteria instead of predefined experiments."""

    # Track which options are available for each selection
    available_module_types = ["Single Modules", "Repeated Modules", "Multiple Modules"]
    available_comm_styles = ["Synchronous", "Asynchronous"]
    available_agent_frameworks = ["ReAct", "Act", "DReAct", "ReDAct"]
    available_defuser_playing = ["With Expert", "Alone"]

    # Start with the first selection - Module Type(s)
    module_types = st.sidebar.multiselect(
        "Module Type(s)", available_module_types, default=["Single Modules"]
    )

    if not module_types:
        st.sidebar.warning("Please select at least one module type")
        return []

    # Update available options based on Module Type selection
    if "Repeated Modules" in module_types:
        # Repeated Modules forces Sync, ReAct, With Expert
        available_comm_styles = ["Synchronous"]
        available_agent_frameworks = ["ReAct"]
        available_defuser_playing = ["With Expert"]

    # Communication Style selection
    comm_styles = (
        st.sidebar.multiselect(
            "Communication Style(s)",
            available_comm_styles,
            default=[available_comm_styles[0]] if available_comm_styles else [],
        )
        if "Repeated Modules" not in module_types
        else ["Synchronous"]
    )

    if not comm_styles and "Repeated Modules" not in module_types:
        st.sidebar.warning("Please select at least one communication style")
        return []

    # Update available options based on Communication Style selection
    if "Asynchronous" in comm_styles:
        # Async forces ReAct, With Expert, and excludes Repeated Modules
        available_agent_frameworks = ["ReAct"]
        available_defuser_playing = ["With Expert"]
        if "Repeated Modules" in module_types:
            st.sidebar.warning("Repeated Modules cannot be used with Asynchronous communication")
            return []

    # Agent Framework selection
    agent_frameworks = (
        st.sidebar.multiselect(
            "Agent Framework(s)",
            available_agent_frameworks,
            default=[available_agent_frameworks[0]] if available_agent_frameworks else [],
        )
        if ("Repeated Modules" not in module_types and "Asynchronous" not in comm_styles)
        else ["ReAct"]
    )

    if (
        not agent_frameworks
        and "Repeated Modules" not in module_types
        and "Asynchronous" not in comm_styles
    ):
        st.sidebar.warning("Please select at least one agent framework")
        return []

    # Update available options based on Agent Framework selection
    if any(framework != "ReAct" for framework in agent_frameworks):
        # Non-ReAct frameworks force Single Module, Sync, With Expert
        available_defuser_playing = ["With Expert"]
        if any(module_type != "Single Modules" for module_type in module_types):
            st.sidebar.warning("Non-ReAct frameworks can only be used with Single Modules")
            return []
        if "Asynchronous" in comm_styles:
            st.sidebar.warning(
                "Non-ReAct frameworks can only be used with Synchronous communication"
            )
            return []

    # Defuser Playing selection
    defuser_playing = (
        st.sidebar.multiselect(
            "Defuser Playing",
            available_defuser_playing,
            default=[available_defuser_playing[0]] if available_defuser_playing else [],
        )
        if (
            "Repeated Modules" not in module_types
            and "Asynchronous" not in comm_styles
            and all(framework == "ReAct" for framework in agent_frameworks)
        )
        else ["With Expert"]
    )

    if not defuser_playing:
        st.sidebar.warning("Please select at least one defuser playing option")
        return []

    # Update available options based on Defuser Playing selection
    if "Alone" in defuser_playing:
        # Playing Alone forces Single Module, Sync, ReAct
        if any(module_type != "Single Modules" for module_type in module_types):
            st.sidebar.warning("Defuser playing alone can only be used with Single Modules")
            return []
        if "Asynchronous" in comm_styles:
            st.sidebar.warning(
                "Defuser playing alone can only be used with Synchronous communication"
            )
            return []
        if any(framework != "ReAct" for framework in agent_frameworks):
            st.sidebar.warning("Defuser playing alone can only be used with ReAct framework")
            return []

    # Manual Access selection (only if Defuser Playing Alone)
    manual_access = None
    if "Alone" in defuser_playing:
        manual_access_options = st.sidebar.multiselect(
            "Manual Access", ["With Manual", "Without Manual"], default=["Without Manual"]
        )

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

    # Now build the criteria based on all selections
    criteria = []

    # Condition criteria
    condition_criteria = []
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

    # Communication style criteria - simplified to just sync and async
    comm_style_values = []
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
        non_react_frameworks = [f.lower() for f in agent_frameworks if f != "ReAct"]
        criteria.append({"config.thinking_framework": {"$in": non_react_frameworks}})
    else:
        # Only ReAct selected
        criteria.append({"config.thinking_framework": "react"})

    # Defuser playing criteria
    if "Alone" in defuser_playing and "With Expert" not in defuser_playing:
        criteria.append({"config.is_playing_alone": True})
    elif "With Expert" in defuser_playing and "Alone" not in defuser_playing:
        criteria.append({"config.is_playing_alone": False})

    # Store in session state for use in fetch_runs
    if "playing_alone" not in st.session_state:
        st.session_state.playing_alone = False
    if "manual_access" not in st.session_state:
        st.session_state.manual_access = False

    st.session_state.playing_alone = "Alone" in defuser_playing
    st.session_state.manual_access = manual_access

    # Store the user's selections in session state for debugging
    if "debug_selections" not in st.session_state:
        st.session_state.debug_selections = {}

    st.session_state.debug_selections = {
        "module_types": module_types,
        "comm_styles": comm_styles,
        "agent_frameworks": agent_frameworks,
        "defuser_playing": defuser_playing,
        "manual_access": manual_access_options if "Alone" in defuser_playing else None,
    }

    return criteria


def get_experiment_criteria(experiment) -> list[dict[str, Any]]:
    if experiment == 1:
        criteria = [{"config.condition": "single_module"}, {"config.communication_style": "sync"}]
        agent_framework = st.sidebar.selectbox(
            "Agent framework (for default use ReAct)",
            ("ReAct", "Act", "DReAct", "ReDAct"),
            index=None,
        )
        if agent_framework:
            criteria.append({"config.thinking_framework": agent_framework.lower()})
            return criteria
        return None
    if experiment == 3:
        criteria = [
            {"config.condition": "single_module"},
            {"config.communication_style": "sync"},
            {"config.is_playing_alone": True},
        ]
        manual = st.sidebar.checkbox("Manual")
        if manual:
            criteria.append({"config.include_manual": True})
            return criteria
        return None
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


def fetch_runs(
    wandb_project: str, experiment_criteria: list, role: Literal["expert", "defuser"]
) -> list[Any] | None:
    """Fetch runs from Weights & Biases API."""
    inclusion_criteria = [
        {"state": "finished"},
        {"summary_metrics.hard_crash": False},
        {"tags": {"$nin": ["old"]}},
        {"config.role": role},
    ]
    inclusion_criteria += experiment_criteria

    return wandb_api.runs(f"{wandb_entity}/{wandb_project}", filters={"$and": inclusion_criteria})


def format_summary_data(summary_json: Any, role: Literal["defuser", "expert"]) -> dict[str, Any]:
    """Format summary data from W&B API."""
    defuser_include_only_keys = [
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

    expert_include_only_keys = ["total_expert_do_nothing_actions", "total_expert_messages_sent"]

    shared_include_only_keys = [
        "total_guardrail_violations",
        "total_invalid_format",
        "total_prompt_truncations",
    ]

    formatted_data = {}
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
    if role == "expert":
        return {"game_id": config_dict["game_id"]}
    include_only_keys = [
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
    formatted_data = {}
    for key, value in config_dict.items():
        if key not in include_only_keys:
            continue
        if key == "optional_widgets":
            formatted_data["num_widgets"] = value
            continue
        formatted_data[key] = value

    return formatted_data


def load_wandb_table(run, table_name):
    """Load a W&B table directly from a run object."""
    artifact_dir = None
    try:
        run_tables = run.logged_artifacts()

        for artifact in run_tables:
            if table_name in artifact.name:
                artifact_dir = artifact.download()

                table_files = []
                for root, _, _files in Path(artifact_dir).glob("**/*.table.json"):
                    table_files.append(root)

                if table_files:
                    with open(table_files[0]) as f:
                        table_data = json.load(f)

                    if "columns" in table_data and "data" in table_data:
                        columns = table_data["columns"]
                        data = table_data["data"]

                        df = pd.DataFrame(data, columns=columns)
                        return pl.from_pandas(df)

        history = run.history()
        if table_name in history.columns:
            table_data = history[table_name].dropna().iloc[0]
            if isinstance(table_data, dict) and "data" in table_data and "columns" in table_data:
                columns = table_data["columns"]
                data = table_data["data"]
                df = pd.DataFrame(data, columns=columns)
                return pl.from_pandas(df)

        return pl.DataFrame()

    except Exception as e:
        if "debug_mode" in st.session_state and st.session_state.debug_mode:
            st.sidebar.error(f"Error loading table {table_name}: {e}")
        return pl.DataFrame()

    finally:
        if artifact_dir and Path(artifact_dir).exists():
            try:
                shutil.rmtree(artifact_dir)
                if "debug_mode" in st.session_state and st.session_state.debug_mode:
                    st.sidebar.info(f"Cleaned up artifact directory: {artifact_dir}")
            except Exception as cleanup_error:
                if "debug_mode" in st.session_state and st.session_state.debug_mode:
                    st.sidebar.warning(f"Failed to clean up artifact directory: {cleanup_error}")


def process_actions_table(actions_df):
    """Process actions table to get counts for each action type."""
    if actions_df.is_empty() or "action" not in actions_df.columns:
        return {}

    action_counts = actions_df.group_by("action").agg(pl.count().alias("count"))

    action_dict = {
        f"{action}_action_count": int(count)
        for action, count in zip(
            action_counts["action"].to_list(), action_counts["count"].to_list(), strict=False
        )
    }

    return action_dict


def process_messages_table(messages_df, role):
    """Process messages table to get statistics."""
    if messages_df.is_empty() or "message" not in messages_df.columns:
        return {}

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

    return {}


def process_reflections_table(reflections_df, role):
    """Process messages table to get statistics."""
    if reflections_df.is_empty() or "message" not in reflections_df.columns:
        return {}

    reflection = reflections_df.select("message").item()

    return {f"reflection_{role}": reflection}


@disk_memoize(max_age_seconds=60 * 60 * 2)
def load_and_process_data(experiment_criteria):
    """Load and process data from Weights & Biases with caching."""
    with st.spinner("Loading and processing data..."):
        status_text = st.empty()
        progress_bar = st.progress(0)

        dfs = {"expert": None, "defuser": None}

        playing_alone = st.session_state.get("playing_alone", False)
        roles_to_process = ["defuser"] if playing_alone else ["expert", "defuser"]

        for role_idx, role in enumerate(roles_to_process):
            status_text.text(f"Fetching {role} runs...")

            runs = fetch_runs(wandb_project, experiment_criteria, role)

            if not runs or len(runs) == 0:
                if role == "expert" and playing_alone:
                    continue
                st.warning(f"No runs found for {role}")
                return None

            total_runs = len(runs)
            status_text.text(f"Processing {role} data ({total_runs} runs)...")

            runs_data = []
            for run_idx, run in enumerate(runs):
                progress = (role_idx * total_runs + run_idx) / (len(roles_to_process) * total_runs)
                progress_bar.progress(progress)

                game_id = run.config.get("game_id")
                config_data = format_config_data(run.config, role)
                summary_data = format_summary_data(run.summary._json_dict, role)

                run_data = {**config_data, **summary_data, f"{role}_run_id": run.id}

                status_text.text(
                    f"Processing {role} run {run_idx + 1}/{total_runs} (game {game_id})"
                )

                if role == "defuser":
                    actions_df = load_wandb_table(run, "actions")
                    if not actions_df.is_empty():
                        action_stats = process_actions_table(actions_df)
                        run_data.update(action_stats)

                messages_df = load_wandb_table(run, "messages")
                if not messages_df.is_empty():
                    message_stats = process_messages_table(messages_df, role)
                    run_data.update(message_stats)

                reflections_df = load_wandb_table(run, "reflections")
                if not reflections_df.is_empty():
                    reflection = process_reflections_table(reflections_df, role)
                    run_data.update(reflection)

                runs_data.append(run_data)

            dfs[role] = pl.DataFrame(runs_data)

        status_text.text("Processing dataframes...")

        for df_name in ["expert", "defuser"]:
            if df_name in dfs and dfs[df_name] is not None and "game_id" in dfs[df_name].columns:
                dfs[df_name] = dfs[df_name].sort("game_id")

        try:
            expert_df = dfs["expert"].clone() if dfs["expert"] is not None else pl.DataFrame()
            defuser_df = dfs["defuser"].clone() if dfs["defuser"] is not None else pl.DataFrame()

            if not expert_df.is_empty():
                rename_dict = {}

                if "total_expert_do_nothing_actions" in expert_df.columns:
                    rename_dict["total_expert_do_nothing_actions"] = (
                        "num_do_nothing_actions_expert"
                    )
                if "total_expert_messages_sent" in expert_df.columns:
                    rename_dict["total_expert_messages_sent"] = "num_messages_sent_expert"
                if "total_guardrail_violations" in expert_df.columns:
                    rename_dict["total_guardrail_violations"] = "num_guardrail_violations_expert"
                if "total_invalid_format" in expert_df.columns:
                    rename_dict["total_invalid_format"] = "num_invalid_format_expert"
                if "total_prompt_truncations" in expert_df.columns:
                    rename_dict["total_prompt_truncations"] = "num_prompt_truncations_expert"

                rename_dict = {k: v for k, v in rename_dict.items() if k in expert_df.columns}
                if rename_dict:
                    expert_df = expert_df.rename(rename_dict)

                cols_to_suffix = [
                    col
                    for col in expert_df.columns
                    if not col.endswith("_expert") and col != "game_id"
                ]
                suffix_dict = {col: f"{col}_expert" for col in cols_to_suffix}
                if suffix_dict:
                    expert_df = expert_df.rename(suffix_dict)

            common_df = None
            if not defuser_df.is_empty():
                rename_dict = {
                    "_runtime": "runtime",
                    "step": "steps",
                    "total_defuser_do_nothing_actions": "num_do_nothing_actions_defuser",
                    "total_defuser_messages_sent": "num_messages_sent_defuser",
                    "total_defuser_actions": "num_actions_defuser",
                    "total_guardrail_violations": "num_guardrail_violations_defuser",
                    "total_invalid_format": "num_invalid_format_defuser",
                    "total_prompt_truncations": "prompt_truncations_defuser",
                }
                rename_dict = {k: v for k, v in rename_dict.items() if k in defuser_df.columns}
                if rename_dict:
                    defuser_df = defuser_df.rename(rename_dict)

                total_cols = [col for col in defuser_df.columns if "total_" in col]
                rename_total_dict = {col: col.replace("total_", "") for col in total_cols}
                if rename_total_dict:
                    defuser_df = defuser_df.rename(rename_total_dict)

                common_df = defuser_df.clone()

                common_cols_to_keep = [
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

                common_cols_to_keep = [
                    col for col in common_cols_to_keep if col in common_df.columns
                ]

                if common_cols_to_keep:
                    common_df = common_df.select(common_cols_to_keep)
                else:
                    common_df = pl.DataFrame({"game_id": defuser_df["game_id"]})

                defuser_cols = ["game_id"]
                if "defuser_run_id" in defuser_df.columns:
                    defuser_cols.append("defuser_run_id")

                standard_metrics = [
                    "num_do_nothing_actions_defuser",
                    "num_messages_sent_defuser",
                    "num_actions_defuser",
                    "num_guardrail_violations_defuser",
                    "num_invalid_format_defuser",
                    "num_prompt_truncations_defuser",
                ]
                defuser_cols.extend([col for col in standard_metrics if col in defuser_df.columns])

                action_cols = [col for col in defuser_df.columns if col.endswith("_action_count")]
                message_cols = [
                    col
                    for col in defuser_df.columns
                    if col.startswith("message_") and col.endswith("defuser")
                ]
                defuser_cols.extend(action_cols)
                defuser_cols.extend(message_cols)

                if len(defuser_cols) > 1:
                    defuser_df = defuser_df.select(defuser_cols)
                else:
                    defuser_df = pl.DataFrame({"game_id": defuser_df["game_id"]})

            try:
                if (
                    not expert_df.is_empty()
                    and not defuser_df.is_empty()
                    and common_df is not None
                ):
                    joined_df = common_df.join(expert_df, on="game_id", how="inner")
                    joined_df = joined_df.join(defuser_df, on="game_id", how="inner")

                    joined_df = joined_df.filter(
                        pl.col("expert_name").is_not_null() & pl.col("defuser_name").is_not_null()
                    )

                    bool_cols = ["is_solved", "is_strike_out", "is_timed_out"]
                    for col in bool_cols:
                        if col in joined_df.columns:
                            joined_df = joined_df.with_columns(
                                pl.col(col).cast(pl.Int32).alias(col)
                            )

                    float_cols = []
                    for col in joined_df.columns:
                        if (
                            joined_df[col].dtype == pl.Float64
                            or joined_df[col].dtype == pl.Float32
                        ):
                            float_cols.append(col)

                    for col in float_cols:
                        joined_df = joined_df.with_columns(
                            pl.col(col).fill_null(0).cast(pl.Int32).alias(col)
                        )

                    for col in joined_df.columns:
                        if col.endswith("_action_count"):
                            joined_df = joined_df.with_columns(
                                pl.col(col).fill_null(0).cast(pl.Int32).alias(col)
                            )

                    for col in joined_df.columns:
                        if col.startswith("message_"):
                            joined_df = joined_df.with_columns(
                                pl.col(col).fill_null(0).cast(pl.Float64).round(2).alias(col)
                            )

                    status_text.empty()
                    progress_bar.empty()

                    return joined_df
                st.warning("One or more dataframes are empty")
                return None
            except Exception as e:
                st.error(f"Error joining dataframes: {e!s}")
                st.exception(e)
                return None

        except Exception as e:
            st.error(f"Error processing dataframes: {e!s}")
            st.exception(e)
            return None


def main() -> None:
    st.title("GPTNT Results Visualizer")

    debug_mode = st.sidebar.checkbox("Debug Mode", value=False)
    st.session_state.debug_mode = debug_mode

    if debug_mode:
        st.sidebar.text(f"Streamlit version: {st.__version__}")
        st.sidebar.text(f"Polars version: {pl.__version__}")

    if st.sidebar.button("Clear Cache"):
        try:
            shutil.rmtree(CACHE_DIR)
            st.sidebar.success("Cache cleared successfully!")
        except Exception as e:
            st.sidebar.error(f"Error clearing cache: {e}")

    st.sidebar.subheader("Select Data Filtering Method")

    filter_method = st.sidebar.radio(
        "Filter Method", ["Predefined Experiment", "Custom Criteria"], index=0
    )

    criteria_changed = False

    if filter_method == "Predefined Experiment":
        st.sidebar.subheader("Select Experiment")

        if "previous_experiment" not in st.session_state:
            st.session_state.previous_experiment = None

        experiment = st.sidebar.selectbox("Experiment #", list(range(1, 8)), index=None)

        if experiment != st.session_state.previous_experiment:
            criteria_changed = True
            st.session_state.previous_experiment = experiment
            st.session_state.data_loaded = False
            st.session_state.df = None

        if not experiment:
            st.info("Please select an experiment number")
            return

        experiment_criteria = get_experiment_criteria(experiment)
    else:
        st.sidebar.subheader("Select Custom Criteria")

        if "previous_custom_criteria" not in st.session_state:
            st.session_state.previous_custom_criteria = None

        experiment = None
        experiment_criteria = get_custom_criteria()

        import json

        criteria_json = json.dumps(experiment_criteria, sort_keys=True)
        if criteria_json != st.session_state.previous_custom_criteria:
            criteria_changed = True
            st.session_state.previous_custom_criteria = criteria_json
            st.session_state.data_loaded = False
            st.session_state.df = None

    if not experiment_criteria:
        st.warning("No criteria selected")
        return

    if debug_mode:
        st.sidebar.subheader("Debug: W&B Query Criteria")

        formatted_criteria = []
        for criterion in experiment_criteria:
            for key, value in criterion.items():
                if isinstance(value, dict) and "$in" in value:
                    formatted_criteria.append(f"{key} in {value['$in']}")
                else:
                    formatted_criteria.append(f"{key} = {value}")

        for criterion in formatted_criteria:
            st.sidebar.text(criterion)

        if filter_method == "Custom Criteria" and "debug_selections" in st.session_state:
            st.sidebar.subheader("Debug: User Selections")
            for key, value in st.session_state.debug_selections.items():
                if value is not None:
                    st.sidebar.text(f"{key}: {value}")

    fetch_button = st.sidebar.button("Fetch runs!")

    if fetch_button or criteria_changed:
        if criteria_changed and not fetch_button:
            st.info("Criteria have changed. Please click 'Fetch runs!' to update the data.")
            return

        st.session_state.data_loaded = False
        st.session_state.df = None

        df = load_and_process_data(experiment_criteria)

        if df is not None and not df.is_empty():
            st.session_state.df = df
            st.session_state.data_loaded = True
            st.success("Data loaded and processed successfully!")

            csv = df.to_pandas().to_csv()
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
        else:
            st.error("Failed to load or process data")
            return

    if st.session_state.data_loaded and st.session_state.df is not None:
        df = st.session_state.df

        main_content = st.container()

        with main_content:
            header_placeholder = st.empty()
            header_placeholder.header("Runs have been fetched!")

        if experiment == 1:
            if len(df.select("expert_name").unique().to_series()) > 0:
                grouped_expert = df.group_by("expert_name").agg(
                    pl.sum("is_solved").alias("solved_count")
                )
                grouped_expert = grouped_expert.sort("solved_count", descending=True)
                best_expert = grouped_expert.row(0)[0]

                if debug_mode:
                    st.sidebar.text(f"Best Expert: {best_expert}")
            else:
                best_expert = None

            if len(df.select("defuser_name").unique().to_series()) > 0:
                grouped_defuser = df.group_by("defuser_name").agg(
                    pl.sum("is_solved").alias("solved_count")
                )
                grouped_defuser = grouped_defuser.sort("solved_count", descending=True)
                best_defuser = grouped_defuser.row(0)[0]

                if debug_mode:
                    st.sidebar.text(f"Best Defuser: {best_defuser}")
            else:
                best_defuser = None
        else:
            expert_options = df.select("expert_name").unique().to_series().drop_nulls().to_list()
            defuser_options = df.select("defuser_name").unique().to_series().drop_nulls().to_list()

            best_expert = st.sidebar.selectbox(
                "Best 'Expert' model", expert_options, index=0 if expert_options else None
            )
            if not best_expert:
                st.warning("Please select a best expert model")
                return

            best_defuser = st.sidebar.selectbox(
                "Best 'Defuser' model", defuser_options, index=0 if defuser_options else None
            )
            if not best_defuser:
                st.warning("Please select a best defuser model")
                return

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
            (
                ~(pl.col("with_same") | pl.col("with_best_expert") | pl.col("with_best_defuser"))
            ).alias("with_rest")
        )

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

            if debug_mode:
                outcome_counts = df.group_by("outcome").count().sort("count", descending=True)
                st.sidebar.write("Outcome distribution:", outcome_counts.to_pandas())

                if "unknown" in df["outcome"].unique():
                    st.sidebar.warning(
                        f"There are still {df.filter(pl.col('outcome') == 'unknown').height} unknown outcomes"
                    )
                else:
                    st.sidebar.success("All outcomes were successfully determined")

        if "numeric_cols" not in st.session_state:
            try:
                for col in df.columns:
                    if (col.endswith("_action_count")) or (
                        col.startswith("message_")
                        and any(
                            x in col
                            for x in ["length_sum", "length_mean", "length_min", "length_max"]
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
                        except Exception as e:
                            if debug_mode:
                                st.sidebar.warning(f"Could not convert {col} to numeric: {e}")

                st.session_state.df = df

                numeric_cols = []
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

                action_message_cols = [
                    col
                    for col in df.columns
                    if (col.endswith("_action_count"))
                    or (
                        col.startswith("message_")
                        and any(
                            x in col
                            for x in ["length_sum", "length_mean", "length_min", "length_max"]
                        )
                    )
                ]

                if debug_mode:
                    st.sidebar.write("Action and message columns found:", action_message_cols)

                    for col in action_message_cols:
                        if col in df.columns:
                            st.sidebar.write(f"Column {col} dtype: {df[col].dtype}")

                for col in action_message_cols:
                    if col not in numeric_cols and col != "seed" and col in df.columns:
                        numeric_cols.append(col)

                st.session_state.numeric_cols = sorted(numeric_cols)

            except Exception as e:
                st.sidebar.error(f"Error getting numeric columns: {e!s}")
                if debug_mode:
                    st.exception(e)
                return

        numeric_cols = st.session_state.numeric_cols

        if not numeric_cols:
            st.warning("No numeric columns found in the data")
            return

        st.sidebar.subheader("Select Metrics and Aggregation Options")

        aggregate_metrics_by = st.sidebar.multiselect(
            "Select metrics to aggregate", numeric_cols, key="aggregate_metrics"
        )

        if not aggregate_metrics_by:
            st.sidebar.info("Please select at least one metric to aggregate")

        create_model_column = st.sidebar.checkbox("Enable model-based analysis", value=False)

        if create_model_column:
            all_models = list(
                set(df["expert_name"].unique().to_list() + df["defuser_name"].unique().to_list())
            )
            all_models = [m for m in all_models if m is not None]
            all_models.sort()

            expert_data = df.clone()
            expert_data = expert_data.with_columns(
                [pl.col("expert_name").alias("model"), pl.lit("expert").alias("role")]
            )

            defuser_data = df.clone()
            defuser_data = defuser_data.with_columns(
                [pl.col("defuser_name").alias("model"), pl.lit("defuser").alias("role")]
            )

            df = pl.concat([expert_data, defuser_data])

            st.info(
                "Data transformed to model-based format. Each row now represents a model in a specific role."
            )

            if debug_mode:
                st.write(f"Unique models: {all_models}")
                st.write(f"New dataframe shape: {df.shape}")

        base_groupby_options = [
            "condition",
            "communication_style",
            "thinking_framework",
            "is_playing_alone",
            "include_manual",
            "seed",
            "num_widgets",
            "outcome",
        ]
        if create_model_column:
            groupby_options = ["model", "role", *base_groupby_options]
        else:
            groupby_options = ["expert_name", "defuser_name", *base_groupby_options]

        if "components" in df.columns:
            groupby_options.append("components")

            sample_row = df.filter(pl.col("components").is_not_null()).head(1)
            if len(sample_row) > 0:
                sample_components = sample_row[0, "components"]

                if isinstance(sample_components, list):
                    df = df.with_columns(pl.col("components").list.first().alias("component_type"))
                    groupby_options.append("component_type")

                    df = df.with_columns(pl.col("components").list.len().alias("num_components"))
                    groupby_options.append("num_components")

                    explode_components = st.sidebar.checkbox(
                        "Explode Components for Analysis", value=False
                    )
                    if explode_components:
                        df = df.explode("components")
                        st.info(
                            "Components have been exploded. Each row now represents a single component."
                        )

        available_groupby = [col for col in groupby_options if col in df.columns]

        if not available_groupby:
            st.warning("No groupby columns available")
            return

        groupby_cols = st.sidebar.multiselect(
            "Group by",
            available_groupby,
            default=[available_groupby[0]] if available_groupby else None,
        )

        agg_functions = st.sidebar.multiselect(
            "Aggregation functions",
            ["mean", "median", "min", "max", "count", "sum"],
            default=["mean", "count"],
        )

        st.sidebar.subheader("Pairing Filters")

        filter_same = st.sidebar.checkbox("Pairings where Expert = Defuser", value=False)

        filter_best = False
        if groupby_cols:
            if "defuser_name" in groupby_cols and "expert_name" not in groupby_cols:
                filter_best = st.sidebar.checkbox(
                    f"Pairings with best expert ({best_expert})", value=False
                )
                if filter_best:
                    df = df.filter(pl.col("with_best_expert"))
            elif "expert_name" in groupby_cols and "defuser_name" not in groupby_cols:
                filter_best = st.sidebar.checkbox(
                    f"Pairings with best defuser ({best_defuser})", value=False
                )
                if filter_best:
                    df = df.filter(pl.col("with_best_defuser"))
            else:
                filter_best_expert = st.sidebar.checkbox(
                    f"Pairings with best expert ({best_expert})", value=False
                )
                filter_best_defuser = st.sidebar.checkbox(
                    f"Pairings with best defuser ({best_defuser})", value=False
                )
                if filter_best_expert:
                    df = df.filter(pl.col("with_best_expert"))
                if filter_best_defuser:
                    df = df.filter(pl.col("with_best_defuser"))

        filter_rest = st.sidebar.checkbox("Other pairings", value=False)

        if filter_same:
            df = df.filter(pl.col("with_same"))
        if filter_rest:
            df = df.filter(pl.col("with_rest"))

        if filter_same or filter_best or filter_rest:
            st.sidebar.info(f"Showing {len(df)} runs after applying filters.")

        if "outcome" in df.columns:
            st.sidebar.subheader("Outcome Filter")

            unique_outcomes = sorted(df["outcome"].unique().to_list())

            selected_outcomes = st.sidebar.multiselect(
                "Filter by outcomes", options=unique_outcomes, default=unique_outcomes
            )

            if selected_outcomes and len(selected_outcomes) < len(unique_outcomes):
                df = df.filter(pl.col("outcome").is_in(selected_outcomes))
                st.sidebar.info(
                    f"Showing {len(df)} runs with outcomes: {', '.join(selected_outcomes)}"
                )

        confirm_aggregate = st.sidebar.button("Aggregate!")

        if confirm_aggregate and aggregate_metrics_by and groupby_cols and agg_functions:
            st.subheader("Aggregation Results")

            try:
                agg_exprs = []
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

                aggregated_df = df.group_by(groupby_cols).agg(agg_exprs)

                for col in aggregated_df.columns:
                    if col not in groupby_cols:
                        col_dtype = aggregated_df[col].dtype

                        if str(col_dtype).startswith(("f32", "f64", "decimal")):
                            aggregated_df = aggregated_df.with_columns(
                                pl.col(col).round(2).alias(col)
                            )

                st.dataframe(aggregated_df)

                csv = aggregated_df.to_pandas().to_csv()
                st.download_button(
                    label="Download aggregated data as CSV",
                    data=csv,
                    file_name="aggregated_results.csv",
                    mime="text/csv",
                )

                if st.checkbox("Show visualizations"):
                    for metric in aggregate_metrics_by:
                        st.subheader(f"Visualization for {metric}")

                        if len(groupby_cols) == 1:
                            chart_data = (
                                df.group_by(groupby_cols[0])
                                .agg(pl.mean(metric).alias(metric))
                                .to_pandas()
                            )
                            st.bar_chart(chart_data.set_index(groupby_cols[0]))

                        elif len(groupby_cols) == 2 and "mean" in agg_functions:
                            try:
                                pivot_data = (
                                    df.select([*groupby_cols, metric])
                                    .to_pandas()
                                    .pivot_table(
                                        values=metric,
                                        index=groupby_cols[0],
                                        columns=groupby_cols[1],
                                        aggfunc="mean",
                                    )
                                )
                                st.write(
                                    f"Average {metric} by {groupby_cols[0]} and {groupby_cols[1]}"
                                )
                                st.dataframe(pivot_data)
                            except Exception as e:
                                st.warning(f"Could not create pivot table: {e!s}")

            except Exception as e:
                st.error(f"Error during aggregation: {e!s}")
                if debug_mode:
                    st.exception(e)

    elif fetch_button and not st.session_state.data_loaded:
        st.info("No data was loaded. Please check your criteria and try again.")
    else:
        st.info("Please fetch data first using the 'Fetch runs!' button in the sidebar.")


if __name__ == "__main__":
    main()
