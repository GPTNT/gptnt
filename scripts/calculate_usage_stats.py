"""Streamlit app for analyzing Weave experiment data focused on model+role cost analysis."""

import json
import re
import warnings
from typing import Any

import pandas as pd
import streamlit as st
import structlog
import weave

# Initialize session state
if "weave_data_loaded" not in st.session_state:
    st.session_state.weave_data_loaded = False
if "trace_data" not in st.session_state:
    st.session_state.trace_data = pd.DataFrame()

logger = structlog.get_logger()
warnings.filterwarnings("ignore", message=".*st.experimental_user.*")

# Configure Streamlit page
_ = st.set_page_config(page_title="Weave Model-Role Analysis", page_icon="🎯", layout="wide")


def get_all_categorical_columns(df: pd.DataFrame) -> list[str]:
    """Get all categorical columns consistently across functions."""
    categorical_cols = ["model", "role"]
    if "is_playing_alone" in df.columns:
        categorical_cols.append("is_playing_alone")
    if "include_manual" in df.columns:
        categorical_cols.append("include_manual")
    if "condition" in df.columns:
        categorical_cols.append("condition")
    if "module" in df.columns:
        categorical_cols.append("module")
    return categorical_cols


def get_selected_aggregation_columns(df: pd.DataFrame, selected_agg_by: list[str]) -> list[str]:
    """Get the selected aggregation columns that exist in the dataframe."""
    # Always include model and role as base
    base_cols = ["model", "role"]
    available_cols = [col for col in base_cols if col in df.columns]

    # Add selected aggregation columns
    for col in selected_agg_by:
        if col in df.columns and col not in available_cols:
            available_cols.append(col)

    return available_cols


def clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Clean DataFrame to avoid PyArrow conversion issues in Streamlit."""
    if df.empty:
        return df

    cleaned_df = df.copy()

    # Convert problematic columns to strings
    for col in cleaned_df.columns:
        try:
            # Check if column has mixed types that could cause PyArrow issues
            sample_values = cleaned_df[col].dropna().head(10)
            has_list = any(isinstance(val, list) for val in sample_values)
            has_dict = any(isinstance(val, dict) for val in sample_values)
            has_array = any(hasattr(val, "__array__") for val in sample_values)
            has_other = any(
                not isinstance(val, (list, dict, str, int, float, bool, type(None)))
                and not hasattr(val, "__array__")
                for val in sample_values
            )

            if has_list or has_dict or has_other or has_array:
                # Convert entire column to string representation
                cleaned_df[col] = cleaned_df[col].apply(
                    lambda x: str(x) if x is not None and not pd.isna(x) else None
                )
        except (ValueError, TypeError, AttributeError):
            # If there's any issue, convert to string
            cleaned_df[col] = cleaned_df[col].astype(str)

    return cleaned_df


def extract_tokens_from_output(output_value: Any) -> dict[str, int]:
    """Extract input_tokens and output_tokens from output.usage."""
    if pd.isna(output_value) or output_value is None:
        return {"input_tokens": None, "output_tokens": None}

    try:
        # Handle JSON strings
        if isinstance(output_value, str):
            try:
                output_dict = json.loads(output_value)
            except json.JSONDecodeError:
                return {"input_tokens": None, "output_tokens": None}
        elif isinstance(output_value, dict):
            output_dict = output_value
        else:
            return {"input_tokens": None, "output_tokens": None}

        # Extract from output.usage
        usage = output_dict.get("usage", {})
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", None)
            output_tokens = usage.get("output_tokens", None)

            # Convert to int if possible, keep None if not
            try:
                input_tokens = int(input_tokens) if input_tokens is not None else None
            except (ValueError, TypeError):
                input_tokens = None

            try:
                output_tokens = int(output_tokens) if output_tokens is not None else None
            except (ValueError, TypeError):
                output_tokens = None

            return {"input_tokens": input_tokens, "output_tokens": output_tokens}

    except (ValueError, TypeError, AttributeError):
        pass

    return {"input_tokens": None, "output_tokens": None}


def calculate_turn_durations(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate turn durations using started_at and ended_at timestamps."""
    if df.empty:
        return df

    df_with_durations = df.copy()

    # Calculate turn duration for each row where we have both timestamps
    if "started_at" in df.columns and "ended_at" in df.columns:
        # Convert to datetime if they're strings
        if df["started_at"].dtype == "object":
            df_with_durations["started_at"] = pd.to_datetime(df_with_durations["started_at"])
        if df["ended_at"].dtype == "object":
            df_with_durations["ended_at"] = pd.to_datetime(df_with_durations["ended_at"])

        # Calculate duration in seconds
        df_with_durations["turn_duration"] = (
            df_with_durations["ended_at"] - df_with_durations["started_at"]
        ).dt.total_seconds()

        # Only keep positive durations
        df_with_durations.loc[df_with_durations["turn_duration"] <= 0, "turn_duration"] = None
    else:
        df_with_durations["turn_duration"] = None

    return df_with_durations


def fix_negative_tokens_with_max(df: pd.DataFrame) -> pd.DataFrame:
    """Fix negative token values by substituting with the maximum non-negative value within the
    same game_id + role combination."""
    if df.empty:
        return df

    df_fixed = df.copy()

    # First, ensure we have the required columns
    if "game_id" not in df_fixed.columns or "role" not in df_fixed.columns:
        return df_fixed

    negative_replacements = 0

    # Group by game_id + role combination
    for (_game_id, _role), group in df_fixed.groupby(["game_id", "role"]):
        group_indices = group.index

        # Handle input_tokens
        if "input_tokens" in df_fixed.columns:
            input_tokens = group["input_tokens"].dropna()
            if len(input_tokens) > 0:
                # Find the maximum non-negative value
                non_negative_input = input_tokens[input_tokens >= 0]
                if len(non_negative_input) > 0:
                    max_input = non_negative_input.max()
                    # Replace all negative values with the max
                    negative_mask = (
                        df_fixed.loc[group_indices, "input_tokens"] < 0
                    ) & df_fixed.loc[group_indices, "input_tokens"].notna()
                    if negative_mask.any():
                        df_fixed.loc[group_indices[negative_mask], "input_tokens"] = max_input
                        negative_replacements += negative_mask.sum()
                else:
                    # If no non-negative values, set negatives to 0
                    negative_mask = (
                        df_fixed.loc[group_indices, "input_tokens"] < 0
                    ) & df_fixed.loc[group_indices, "input_tokens"].notna()
                    if negative_mask.any():
                        df_fixed.loc[group_indices[negative_mask], "input_tokens"] = 0
                        negative_replacements += negative_mask.sum()

        # Handle output_tokens
        if "output_tokens" in df_fixed.columns:
            output_tokens = group["output_tokens"].dropna()
            if len(output_tokens) > 0:
                # Find the maximum non-negative value
                non_negative_output = output_tokens[output_tokens >= 0]
                if len(non_negative_output) > 0:
                    max_output = non_negative_output.max()
                    # Replace all negative values with the max
                    negative_mask = (
                        df_fixed.loc[group_indices, "output_tokens"] < 0
                    ) & df_fixed.loc[group_indices, "output_tokens"].notna()
                    if negative_mask.any():
                        df_fixed.loc[group_indices[negative_mask], "output_tokens"] = max_output
                        negative_replacements += negative_mask.sum()
                else:
                    # If no non-negative values, set negatives to 0
                    negative_mask = (
                        df_fixed.loc[group_indices, "output_tokens"] < 0
                    ) & df_fixed.loc[group_indices, "output_tokens"].notna()
                    if negative_mask.any():
                        df_fixed.loc[group_indices[negative_mask], "output_tokens"] = 0
                        negative_replacements += negative_mask.sum()

    if negative_replacements > 0:
        st.info(
            f"Fixed {negative_replacements} negative token values using max values per game+role combination"
        )

    return df_fixed


def extract_experiment_name_from_attributes(attributes_value: Any) -> str | None:
    """Extract experiment_name from attributes."""
    if pd.isna(attributes_value) or attributes_value is None:
        return None

    try:
        # Handle JSON strings
        if isinstance(attributes_value, str):
            try:
                attributes_dict = json.loads(attributes_value)
            except json.JSONDecodeError:
                return None
        elif isinstance(attributes_value, dict):
            attributes_dict = attributes_value
        else:
            return None

        # Extract experiment_name directly
        return attributes_dict.get("experiment_name", None)

    except (ValueError, TypeError, AttributeError):
        return None


def extract_game_id_from_attributes(attributes_value: Any) -> str | None:
    """Extract game_id from attributes."""
    if pd.isna(attributes_value) or attributes_value is None:
        return None

    try:
        # Handle JSON strings
        if isinstance(attributes_value, str):
            try:
                attributes_dict = json.loads(attributes_value)
            except json.JSONDecodeError:
                return None
        elif isinstance(attributes_value, dict):
            attributes_dict = attributes_value
        else:
            return None

        # Extract game_id directly
        return attributes_dict.get("game_id", None)

    except (ValueError, TypeError, AttributeError):
        return None


def extract_is_playing_alone_from_attributes(attributes_value: Any) -> bool | None:
    """Extract is_playing_alone from attributes."""
    if pd.isna(attributes_value) or attributes_value is None:
        return None

    try:
        # Handle JSON strings
        if isinstance(attributes_value, str):
            try:
                attributes_dict = json.loads(attributes_value)
            except json.JSONDecodeError:
                return None
        elif isinstance(attributes_value, dict):
            attributes_dict = attributes_value
        else:
            return None

        # Extract is_playing_alone directly
        return attributes_dict.get("is_playing_alone", None)

    except (ValueError, TypeError, AttributeError):
        return None


def extract_include_manual_from_attributes(attributes_value: Any) -> bool | None:
    """Extract include_manual from attributes."""
    if pd.isna(attributes_value) or attributes_value is None:
        return None

    try:
        # Handle JSON strings
        if isinstance(attributes_value, str):
            try:
                attributes_dict = json.loads(attributes_value)
            except json.JSONDecodeError:
                return None
        elif isinstance(attributes_value, dict):
            attributes_dict = attributes_value
        else:
            return None

        # Extract include_manual directly
        return attributes_dict.get("include_manual", None)

    except (ValueError, TypeError, AttributeError):
        return None


def extract_condition_from_attributes(attributes_value: Any) -> str | None:
    """Extract condition from attributes."""
    if pd.isna(attributes_value) or attributes_value is None:
        return None

    try:
        # Handle JSON strings
        if isinstance(attributes_value, str):
            try:
                attributes_dict = json.loads(attributes_value)
            except json.JSONDecodeError:
                return None
        elif isinstance(attributes_value, dict):
            attributes_dict = attributes_value
        else:
            return None

        # Extract condition directly
        return attributes_dict.get("condition", None)

    except (ValueError, TypeError, AttributeError):
        return None


def extract_thinking_framework_from_attributes(attributes_value: Any) -> str | None:
    """Extract thinking_framework from attributes."""
    if pd.isna(attributes_value) or attributes_value is None:
        return None

    try:
        # Handle JSON strings
        if isinstance(attributes_value, str):
            try:
                attributes_dict = json.loads(attributes_value)
            except json.JSONDecodeError:
                return None
        elif isinstance(attributes_value, dict):
            attributes_dict = attributes_value
        else:
            return None

        # Extract thinking_framework directly
        return attributes_dict.get("thinking_framework", None)

    except (ValueError, TypeError, AttributeError):
        return None


def extract_module_from_experiment_name(experiment_name: str) -> str | None:
    """Extract module from experiment name (e.g., 'Password' from
    'repeated_modules_2_sync_Password_337_(defuser=claude37+react--expert=claude')."""
    if pd.isna(experiment_name) or not isinstance(experiment_name, str):
        return None

    try:
        # First try: look for pattern _ModuleName_digits_(
        match = re.search(r"_([^_]+)_\d+_\(", experiment_name)
        if match:
            return match.group(1)

        # Second try: look for pattern _ModuleName_digits at the end
        match = re.search(r"_([^_]+)_\d+$", experiment_name)
        if match:
            return match.group(1)

        # Third try: more flexible - find any word followed by _digits
        match = re.search(r"_([A-Za-z][A-Za-z0-9]*)_\d+", experiment_name)
        if match:
            return match.group(1)

    except (ValueError, TypeError, AttributeError):
        pass

    return None


def process_weave_data(df: pd.DataFrame) -> pd.DataFrame:
    """Process the DataFrame to extract all needed fields."""
    if df.empty:
        return df

    processed_df = df.copy()

    # Extract tokens from output
    if "output" in processed_df.columns:
        token_data = processed_df["output"].apply(extract_tokens_from_output)
        token_df = pd.DataFrame(token_data.tolist())
        processed_df = pd.concat([processed_df, token_df], axis=1)

    # Extract all fields from attributes
    if "attributes" in processed_df.columns:
        processed_df["experiment_name"] = processed_df["attributes"].apply(
            extract_experiment_name_from_attributes
        )
        processed_df["game_id"] = processed_df["attributes"].apply(extract_game_id_from_attributes)
        processed_df["is_playing_alone"] = processed_df["attributes"].apply(
            extract_is_playing_alone_from_attributes
        )
        processed_df["include_manual"] = processed_df["attributes"].apply(
            extract_include_manual_from_attributes
        )
        processed_df["thinking_framework"] = processed_df["attributes"].apply(
            extract_thinking_framework_from_attributes
        )
        processed_df["condition"] = processed_df["attributes"].apply(
            extract_condition_from_attributes
        )

    # Extract condition and module from experiment_name
    if "experiment_name" in processed_df.columns:
        processed_df["module"] = processed_df["experiment_name"].apply(
            extract_module_from_experiment_name
        )

        # Set module to 'N/A' when condition is 'multiple_modules'
        if "condition" in processed_df.columns:
            multiple_modules_mask = processed_df["condition"].str.contains(
                "multiple_modules", na=False
            )
            processed_df.loc[multiple_modules_mask, "module"] = "N/A"

    return processed_df


class WeaveModelRoleAnalyzer:
    """Class for analyzing Weave traces by model and role."""

    def __init__(self, project_name: str) -> None:
        """Initialize the analyzer with a Weave project."""
        self.project_name = project_name
        self.client: Any = None

    def connect_to_weave(self) -> bool:
        """Connect to Weave project."""
        try:
            self.client = weave.init(self.project_name)

            if self.client is None:
                _ = st.error("weave.init() returned None - check project name format")
                return False

        except (ValueError, TypeError, AttributeError, ConnectionError) as e:
            _ = st.error(f"Failed to connect to Weave: {e!s}")
            return False
        else:
            return True

    def fetch_model_role_traces(
        self,
        models: list[str],
        roles: list[str],
        limit: int | None = None,
        page_size: int | None = None,
    ) -> pd.DataFrame:
        """Fetch traces filtered by models and roles and return as DataFrame."""
        if not self.client:
            return pd.DataFrame()

        all_dataframes = []

        # If "All" is selected, get all combinations
        if len(models) == 1 and models[0] == "All":
            models = [
                "claude37",
                "gemini-2",
                "gemini-25",
                "gemini-25pro",
                "gpt41",
                "gpt4o",
                "gpt4o-mini",
            ]

        if len(roles) == 1 and roles[0] == "All":
            roles = ["defuser", "expert"]

        # Fetch traces for each model-role combination
        for model in models:
            for role in roles:
                df = self._fetch_single_model_role(model, role, limit, page_size)
                if not df.empty:
                    # Add model and role columns
                    df["model"] = model
                    df["role"] = role
                    all_dataframes.append(df)

        if all_dataframes:
            combined_df = pd.concat(all_dataframes, ignore_index=True)
            return combined_df
        return pd.DataFrame()

    def _fetch_single_model_role(
        self, model: str, role: str, limit: int | None = None, page_size: int | None = None
    ) -> pd.DataFrame:
        """Fetch traces for a single model-role combination and return as DataFrame."""
        try:
            query = {
                "$expr": {
                    "$contains": {
                        "input": {"$getField": "op_name"},
                        "substr": {"$literal": f"{model}-{role}"},
                        "case_insensitive": True,
                    }
                }
            }

            call_params = {
                "query": query,
                "columns": ["started_at", "ended_at", "output", "attributes"],
                "sort_by": [{"field": "started_at", "direction": "desc"}],
            }

            if limit is not None:
                call_params["limit"] = limit

            if page_size is not None:
                call_params["page_size"] = page_size

            calls = self.client.get_calls(**call_params)
            df = self._process_calls_to_dataframe(calls)

            if not df.empty:
                return df
            return pd.DataFrame()

        except (ValueError, TypeError, AttributeError, ConnectionError):
            return pd.DataFrame()

    def _process_calls_to_dataframe(self, calls) -> pd.DataFrame:
        """Process calls using to_pandas to avoid iterator consumption."""
        try:
            if hasattr(calls, "to_pandas"):
                df = calls.to_pandas()

                if df.empty:
                    return pd.DataFrame()

                # Process the DataFrame to extract our needed fields
                processed_df = process_weave_data(df)
                return processed_df

            return pd.DataFrame()

        except (ValueError, TypeError, AttributeError):
            return pd.DataFrame()


def process_model_role_data(df: pd.DataFrame) -> pd.DataFrame:
    """Process the combined DataFrame and add turn indices."""
    if df.empty:
        return df

    # Check for essential columns
    essential_columns = ["role", "model"]
    for col in essential_columns:
        if col not in df.columns:
            return pd.DataFrame()

    # Filter to rows with required data
    mask = df["role"].notna() & df["model"].notna()
    valid_df = df[mask].copy()

    if valid_df.empty:
        return pd.DataFrame()

    # Filter to only include rows where thinking_framework is 'react'
    if "thinking_framework" in valid_df.columns:
        react_mask = valid_df["thinking_framework"] == "react"
        valid_df = valid_df[react_mask].copy()

        if valid_df.empty:
            st.warning("No rows found with thinking_framework = 'react'")
            return pd.DataFrame()

    # We should now have game_id from attributes
    if "game_id" not in valid_df.columns or valid_df["game_id"].isna().all():
        _ = st.error("No game_id found in attributes - this shouldn't happen!")
        return pd.DataFrame()

    # Calculate turn durations using timestamps
    valid_df = calculate_turn_durations(valid_df)

    # Get ALL categorical columns consistently
    categorical_cols = get_all_categorical_columns(valid_df)

    # Sort by ALL grouping columns plus started_at to establish turn order
    grouping_cols = ["game_id", *categorical_cols]
    if "started_at" in valid_df.columns:
        valid_df = valid_df.sort_values([*grouping_cols, "started_at"])
    else:
        valid_df = valid_df.sort_values(grouping_cols)

    # Add turn index for each unique combination using ALL categorical columns
    valid_df["turn_idx"] = valid_df.groupby(grouping_cols).cumcount()

    # Fix negative tokens using max values per game_id + role combination
    valid_df = fix_negative_tokens_with_max(valid_df)

    return valid_df


def create_per_game_aggregation(df: pd.DataFrame, selected_agg_by: list[str]) -> pd.DataFrame:
    """Create per-game aggregation statistics with configurable aggregation columns."""
    if df.empty:
        return pd.DataFrame()

    # Check required columns
    required_cols = ["game_id", "model", "role"]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        return pd.DataFrame()

    # Get selected aggregation columns that exist in the dataframe
    categorical_cols = get_selected_aggregation_columns(df, selected_agg_by)

    # Get final turn for each game + categorical columns combination
    grouping_cols = ["game_id", *categorical_cols]

    if "started_at" in df.columns:
        df_sorted = df.sort_values([*grouping_cols, "started_at"])
        final_turns = df_sorted.groupby(grouping_cols).tail(1)
    else:
        if "turn_idx" in df.columns:
            final_turns = df.loc[df.groupby(grouping_cols)["turn_idx"].idxmax()]
        else:
            final_turns = df.groupby(grouping_cols).tail(1)

    # Add total turns for each combination
    if "turn_idx" in final_turns.columns:
        final_turns["total_turns"] = final_turns["turn_idx"] + 1

    # First, get per-game token totals by summing all turns within each game
    agg_dict_per_game = {}

    if "input_tokens" in df.columns and "output_tokens" in df.columns:
        # Sum tokens across all turns for each game+categorical combination
        game_token_totals = (
            df.groupby(grouping_cols)
            .agg({"input_tokens": "sum", "output_tokens": "sum"})
            .reset_index()
        )

        # Add these totals to final_turns
        final_turns = final_turns.merge(
            game_token_totals, on=grouping_cols, suffixes=("", "_total")
        )

        # Use the total tokens for aggregation
        token_cols_to_use = ["input_tokens_total", "output_tokens_total"]
        for token_col in token_cols_to_use:
            if token_col in final_turns.columns:
                agg_dict_per_game[token_col] = ["mean", "max"]

    # Handle turn durations - aggregate by role since each role has their own durations
    if "turn_duration" in df.columns:
        # Calculate average turn duration per role per game
        role_duration_stats = (
            df[df["turn_duration"].notna()]
            .groupby(grouping_cols)["turn_duration"]
            .mean()
            .reset_index()
        )
        role_duration_stats.rename(
            columns={"turn_duration": "avg_turn_duration_per_game"}, inplace=True
        )

        # Merge with final_turns
        final_turns = final_turns.merge(role_duration_stats, on=grouping_cols, how="left")

        if "avg_turn_duration_per_game" in final_turns.columns:
            agg_dict_per_game["avg_turn_duration_per_game"] = ["mean", "max"]

    # Aggregate by the categorical columns (same columns, just without game_id)
    if "total_turns" in final_turns.columns:
        agg_dict_per_game["total_turns"] = ["mean", "max", "count"]

    if not agg_dict_per_game:
        return pd.DataFrame()

    per_game_stats = final_turns.groupby(categorical_cols).agg(agg_dict_per_game).round(2)

    # Flatten column names
    per_game_stats.columns = [
        f"{col[1]}_{col[0]}_per_game" if col[1] else col[0] for col in per_game_stats.columns
    ]
    per_game_stats = per_game_stats.reset_index()

    # Rename columns for clarity
    rename_dict = {
        "count_total_turns_per_game": "total_games",
        "mean_total_turns_per_game": "avg_turns_per_game",
        "max_total_turns_per_game": "max_turns_per_game",
        "mean_input_tokens_total_per_game": "avg_input_tokens_per_game",
        "max_input_tokens_total_per_game": "max_input_tokens_per_game",
        "mean_output_tokens_total_per_game": "avg_output_tokens_per_game",
        "max_output_tokens_total_per_game": "max_output_tokens_per_game",
        "mean_avg_turn_duration_per_game_per_game": "avg_turn_duration_seconds",
        "max_avg_turn_duration_per_game_per_game": "max_turn_duration_seconds",
    }
    per_game_stats = per_game_stats.rename(columns=rename_dict)

    return per_game_stats


def create_overview_metrics(df: pd.DataFrame) -> None:
    """Create overview metrics."""
    if df.empty:
        return

    _ = st.subheader("🎯 Overview")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if "game_id" in df.columns:
            _ = st.metric("Total Games", df["game_id"].nunique())
        else:
            _ = st.metric("Total Games", "N/A")
    with col2:
        _ = st.metric("Total Turns", len(df))
    with col3:
        if "input_tokens" in df.columns and "output_tokens" in df.columns:
            total_tokens = df["input_tokens"].sum() + df["output_tokens"].sum()
            _ = st.metric("Total Tokens", f"{total_tokens:,}")
        else:
            _ = st.metric("Total Tokens", "N/A")
    with col4:
        if "input_tokens" in df.columns and "output_tokens" in df.columns:
            avg_tokens = df["input_tokens"].mean() + df["output_tokens"].mean()
            _ = st.metric("Avg Tokens/Turn", f"{avg_tokens:.0f}")
        else:
            _ = st.metric("Avg Tokens/Turn", "N/A")

    # Additional overview metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        _ = st.metric("Models Analyzed", df["model"].nunique())
    with col2:
        if "condition" in df.columns:
            _ = st.metric("Conditions", df["condition"].nunique())
        else:
            _ = st.metric("Conditions", "N/A")
    with col3:
        if "module" in df.columns:
            _ = st.metric("Modules", df["module"].nunique())
        else:
            _ = st.metric("Modules", "N/A")
    with col4:
        # Show average turn duration if available
        if "turn_duration" in df.columns:
            avg_duration = df["turn_duration"].mean()
            if pd.notna(avg_duration):
                _ = st.metric("Avg Turn Duration", f"{avg_duration:.1f}s")
            else:
                _ = st.metric("Avg Turn Duration", "N/A")
        elif "is_playing_alone" in df.columns:
            _ = st.metric("Playing Alone Variations", df["is_playing_alone"].nunique())
        elif "include_manual" in df.columns:
            _ = st.metric("Manual Variations", df["include_manual"].nunique())
        else:
            _ = st.metric("", "")


def create_analysis_tables(per_game_stats: pd.DataFrame) -> None:
    """Create analysis tables."""
    if per_game_stats.empty:
        st.warning("No aggregated data available")
        return

    display_df = clean_dataframe_for_display(per_game_stats)
    st.dataframe(display_df, use_container_width=True)

    csv = per_game_stats.to_csv(index=False)
    st.download_button(
        label="Download Aggregated Stats",
        data=csv,
        file_name="weave_aggregated_stats.csv",
        mime="text/csv",
        key="download_aggregated",
    )


def fetch_and_process_model_role_data() -> bool:
    """Fetch and process data for all models and roles."""
    project_name = st.session_state.get("weave_project_name", "")

    if not project_name:
        _ = st.error("Please enter a Weave project name")
        return False

    # Use all models and roles instead of selected ones
    all_models = ["All"]  # This will expand to all models in the fetch method
    all_roles = ["All"]  # This will expand to all roles in the fetch method

    with st.spinner("Fetching and processing data..."):
        analyzer = WeaveModelRoleAnalyzer(project_name)

        if not analyzer.connect_to_weave():
            return False

        limit = st.session_state.get("fetch_limit")
        page_size = st.session_state.get("page_size")

        raw_df = analyzer.fetch_model_role_traces(
            models=all_models, roles=all_roles, limit=limit, page_size=page_size
        )

        if raw_df.empty:
            _ = st.error("No traces found")
            return False

        # Process the DataFrame (add turn indices, etc.)
        trace_df = process_model_role_data(raw_df)

        if trace_df.empty:
            _ = st.error("No valid traces with required fields found")
            return False

        st.session_state.trace_data = trace_df
        st.session_state.weave_data_loaded = True

        game_count = trace_df["game_id"].nunique() if "game_id" in trace_df.columns else "N/A"
        condition_count = (
            trace_df["condition"].nunique() if "condition" in trace_df.columns else "N/A"
        )

        # Show duration data availability
        duration_available = (
            "turn_duration" in trace_df.columns and trace_df["turn_duration"].notna().any()
        )

        duration_info = ""
        if duration_available:
            avg_duration = trace_df["turn_duration"].mean()
            duration_info = f" (Avg turn duration: {avg_duration:.1f}s)"

        _ = st.success(
            f"Loaded {len(trace_df)} traces from {game_count} games "
            f"across {condition_count} conditions for "
            f"{trace_df['model'].nunique()} models and {trace_df['role'].nunique()} roles{duration_info}"
        )
        return True


def main() -> None:
    """Main function for the Weave Model-Role Analysis app."""
    _ = st.title("🎯 Weave Model-Role Analysis")

    # Sidebar configuration
    with st.sidebar:
        _ = st.header("🔧 Configuration")

        project_name = st.text_input(
            "Weave Project Name",
            value="gptnt/for-real",
            placeholder="entity/project-name",
            help="Enter your Weave project name",
        )
        st.session_state.weave_project_name = project_name

        _ = st.subheader("⚙️ Advanced Options")

        # Limit option with "No Limit" checkbox
        use_limit = st.checkbox("Use Limit", value=True, help="Uncheck for no limit (may be slow)")

        if use_limit:
            limit = st.number_input(
                "Limit",
                min_value=100,
                max_value=50000,
                value=5000,
                help="Number of traces to fetch per model-role combination",
            )
            st.session_state.fetch_limit = limit
        else:
            st.session_state.fetch_limit = None

        # Page size option with "No Page Size" checkbox
        use_page_size = st.checkbox(
            "Use Page Size", value=True, help="Uncheck for no page size limit"
        )

        if use_page_size:
            page_size = st.number_input(
                "Page Size",
                min_value=50,
                max_value=1000,
                value=200,
                help="Number of traces to fetch per page",
            )
            st.session_state.page_size = page_size
        else:
            st.session_state.page_size = None

        fetch_button = st.button("Analyze All Models + Roles", type="primary")

    # Fetch data
    if fetch_button:
        data_loaded = fetch_and_process_model_role_data()
        if not data_loaded:
            return

    # Display analysis if data is loaded
    if st.session_state.get("weave_data_loaded", False) and not st.session_state.trace_data.empty:
        df = st.session_state.trace_data

        # Debug: Show available columns
        st.write("Available columns:", df.columns.tolist())

        # Create overview
        create_overview_metrics(df)

        # Aggregation options
        st.subheader("📊 Analysis Configuration")

        # Available aggregation options
        agg_options = []
        if "model" in df.columns:
            agg_options.append("model")
        if "role" in df.columns:
            agg_options.append("role")
        if "condition" in df.columns:
            agg_options.append("condition")
        if "module" in df.columns:
            agg_options.append("module")
        if "is_playing_alone" in df.columns:
            agg_options.append("is_playing_alone")
        if "include_manual" in df.columns:
            agg_options.append("include_manual")

        selected_agg_by = st.multiselect(
            "Aggregate by:",
            options=agg_options,
            default=["model", "role"],
            help="Select which dimensions to aggregate the data by",
        )

        if not selected_agg_by:
            st.warning("Please select at least one aggregation dimension")
            return

        # Create per-game aggregation with selected dimensions
        per_game_stats = create_per_game_aggregation(df, selected_agg_by)

        if per_game_stats.empty:
            st.warning("No aggregated data available")
            return

        # Create analysis tables
        create_analysis_tables(per_game_stats)

        # Download raw data
        with st.expander("📥 Download Raw Data"):
            st.download_button(
                label="Download Raw Data (All Columns)",
                data=df.to_csv(index=False),
                file_name="weave_raw_data_complete.csv",
                mime="text/csv",
                key="download_raw_complete",
            )

    else:
        _ = st.info("👆 Enter a project name and click 'Analyze All Models + Roles' to begin")


if __name__ == "__main__":
    main()
