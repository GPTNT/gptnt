from __future__ import annotations

from typing import Any

import streamlit as st
from caseconverter import titlecase
from pydantic.dataclasses import dataclass


@dataclass
class Filters:
    """Filters for experiments."""

    condition: list[str]
    communication_style: list[str]
    modules: list[str]
    defuser: list[str]
    expert: list[str]
    seed: list[int]

    modules_filter_type: str = "Include All"  # or "Include Any"


def render_filter_pills(
    options: Filters,
    *,
    presets: dict[str, Filters] | None = None,  # noqa: ARG001
) -> Filters:
    """Render filter pills UI for experiment filtering.

    Stateless: takes available options and returns selected filter values.
    The returned Filters is suitable for passing directly to ``apply_filters()``.

    Args:
        options: Available filter options derived from scanned experiments.
        presets: Optional named presets that pre-populate filter selections.
                 Keys are preset display names, values are dicts matching the
                 return format of this function. (UI not yet implemented —
                 this is a hook for future experiment-config filter shortcuts.)
    """
    filters: dict[str, Any] = {}

    with st.expander(":small[Filter Experiments]", icon=":material/filter_list:", expanded=False):
        _ = st.caption(
            "Select one or more values for each. Empty means no filtering on that attribute."
        )

        selected_conditions = st.pills(
            "**Conditions**",
            options=options.condition,
            selection_mode="multi",
            default=None,
            format_func=titlecase,
        )
        filters["condition"] = selected_conditions if selected_conditions else []

        selected_comm_styles = st.pills(
            "**Communication Style**",
            options=options.communication_style,
            selection_mode="multi",
            default=None,
            format_func=titlecase,
        )
        filters["communication_style"] = selected_comm_styles if selected_comm_styles else []

        module_filter_type = st.segmented_control(
            "**Modules Filter Type**",
            options=["Include All", "Include Any"],
            default="Include All",
            help=(
                "When filtering by modules, 'Include All' means the experiment must contain ALL "
                "selected modules. 'Include Any' means the experiment must contain at least one "
                "of the selected modules."
            ),
        )
        if not module_filter_type:
            _ = st.error("Please select a filter type for modules.")
        filters["modules_filter_type"] = module_filter_type

        selected_modules = st.pills(
            "**Modules**",
            options=options.modules,
            selection_mode="multi",
            default=None,
            format_func=titlecase,
        )
        filters["modules"] = selected_modules if selected_modules else []

        selected_defusers = st.pills(
            "**Defuser**", options=options.defuser, selection_mode="multi", default=None
        )
        filters["defuser"] = selected_defusers if selected_defusers else []

        selected_experts = st.pills(
            "**Expert**", options=options.expert, selection_mode="multi", default=None
        )
        filters["expert"] = selected_experts if selected_experts else []

        selected_seeds = st.pills(
            "**Seed**", options=options.seed, selection_mode="multi", default=None, format_func=str
        )
        filters["seed"] = selected_seeds if selected_seeds else []

    return Filters(**filters)
