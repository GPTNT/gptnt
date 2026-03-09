from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, get_args, override

import streamlit as st
import yaml
from caseconverter import titlecase
from more_itertools import flatten

from gptnt.experiments.experiments import Condition
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.players.specification import CommunicationStyle

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from gptnt.app.experiment_loader.scanner import ScannedExperiment


type ModuleFilterType = Literal["Include All", "Include Any"]
type OutcomeType = Literal["Solved", "Strike Out", "Timeout"]


@st.cache_data()
def _load_available_players() -> list[str]:
    model_dir = Path("configs/models")
    player_names = []
    for model_file in model_dir.glob("*.yaml"):
        loaded = yaml.safe_load(model_file.read_bytes())
        player_name = loaded["capabilities"]["player_name"]
        player_names.append(player_name)

    return sorted(set(player_names))


ALL_CONDITIONS = list(get_args(Condition.__value__))
ALL_COMMUNICATION_STYLES = list(get_args(CommunicationStyle.__value__))
ALL_MODULES = sorted({component.value for component in KtaneComponent})
ALL_PLAYERS = _load_available_players()


@dataclass()
class Filters:
    """Filters for experiments."""

    condition: Sequence[str] = field(default_factory=list)
    communication_style: Sequence[str] = field(default_factory=list)
    modules: Sequence[str] = field(default_factory=list)
    defuser: Sequence[str] = field(default_factory=list)
    expert: Sequence[str] = field(default_factory=list)
    seed: Sequence[int] = field(default_factory=list)
    name: Sequence[str] = field(default_factory=list)
    strikes: Sequence[int] = field(default_factory=list)
    outcome: Sequence[OutcomeType] = field(default_factory=list)
    tags: Sequence[str] = field(default_factory=list)
    modules_filter_type: ModuleFilterType = field(default="Include All")
    time_remaining: float = field(default=0)

    @override
    def __hash__(self) -> int:
        """Custom hash implementation to allow caching with mutable default fields."""
        return hash(
            (
                tuple(self.condition),
                tuple(self.communication_style),
                tuple(self.modules),
                tuple(self.defuser),
                tuple(self.expert),
                tuple(self.seed),
                tuple(self.name),
                tuple(self.strikes),
                tuple(self.outcome),
                tuple(self.tags),
                self.modules_filter_type,
                self.time_remaining,
            )
        )

    @classmethod
    def from_experiments(cls, experiments: list[ScannedExperiment]) -> Filters:
        """Derive available filter options from a list of scanned experiments.

        Uses the full set of valid conditions, communication styles, and modules from the type
        definitions, and derives defusers, experts, and seeds from the actual scanned data.
        """
        if experiments:
            defuser = sorted({exp.defuser for exp in experiments if exp.defuser})
            expert = sorted({exp.expert for exp in experiments if exp.expert})
            seed = sorted({exp.seed for exp in experiments if exp.seed})
        else:
            defuser = ALL_PLAYERS
            expert = [*ALL_PLAYERS, "None"]
            seed = []
        return Filters(
            condition=ALL_CONDITIONS,
            communication_style=ALL_COMMUNICATION_STYLES,
            modules=ALL_MODULES,
            defuser=defuser,
            expert=expert,
            seed=seed,
            modules_filter_type="Include All",
            name=[exp.name for exp in experiments],
            tags=list(set(flatten(exp.tags for exp in experiments if exp.tags))),
        )


OUTCOME_CHECKS: dict[OutcomeType, Callable[[ScannedExperiment], bool]] = {  # noqa: WPS407
    "Solved": lambda exp: exp.is_solved,
    "Strike Out": lambda exp: exp.is_strike_out,
    "Timeout": lambda exp: exp.is_timeout,
}


def _build_predicates(filters: Filters) -> list[Callable[[ScannedExperiment], bool]]:  # noqa: WPS231
    """Build a list of predicate functions based on the selected filters."""
    predicates: list[Callable[[ScannedExperiment], bool]] = []

    for attr, selected_values in (  # noqa: WPS426
        ("condition", filters.condition),
        ("communication_style", filters.communication_style),
        ("defuser", filters.defuser),
        ("expert", filters.expert),
        ("seed", filters.seed),
        ("strike_count", filters.strikes),
    ):
        if selected_values:
            predicates.append(
                lambda exp, attr=attr, selected_values=selected_values: getattr(exp, attr)
                in selected_values
            )

    if filters.modules:
        selected = frozenset(filters.modules)
        if filters.modules_filter_type == "Include All":
            predicates.append(lambda exp, selected=selected: selected.issubset(exp.modules or []))
        else:
            predicates.append(
                lambda exp, selected=selected: not selected.isdisjoint(exp.modules or [])
            )

    if filters.tags:
        selected = frozenset(filters.tags)
        predicates.append(lambda exp, selected=selected: not selected.isdisjoint(exp.tags or []))

    if filters.name:
        predicates.append(
            lambda exp, name=filters.name: all(part.lower() in exp.name.lower() for part in name)
        )

    if filters.time_remaining > 0:
        predicates.append(lambda exp, time=filters.time_remaining: exp.timer_seconds >= time)

    active_outcomes = [fn for key, fn in OUTCOME_CHECKS.items() if key in filters.outcome]
    if active_outcomes:
        predicates.append(lambda exp, checks=active_outcomes: any(check(exp) for check in checks))

    return predicates


def apply_filters(
    scanned_experiments: list[ScannedExperiment], filters: Filters
) -> list[ScannedExperiment]:
    """Apply filters to scanned experiments."""
    predicates = _build_predicates(filters)
    return [exp for exp in scanned_experiments if all(pred(exp) for pred in predicates)]


def _dummy_model_filter_func(model_name: str) -> str:
    """Add an icon if its one of the dummy models."""
    if model_name.startswith("test"):
        return f"{model_name} :yellow[:material/science_off:]"
    return model_name


def render_filter_pills(options: Filters, *, default: Filters) -> Filters:
    """Render filter pills UI for experiment filtering.

    Stateless: takes available options and returns selected filter values.
    The returned Filters is suitable for passing directly to `apply_filters()`.
    """
    filters = default

    filters.condition = st.pills(
        "**Conditions**",
        options=sorted(options.condition),
        selection_mode="multi",
        default=default.condition or None,
        format_func=titlecase,
    )
    with st.container(horizontal=True, width="content", gap="medium"):
        filters.communication_style = st.pills(
            "**Communication Style**",
            options=sorted(options.communication_style),
            selection_mode="multi",
            default=default.communication_style or None,
            format_func=titlecase,
        )
        filters.seed = st.pills(
            "**Seed**",
            options=sorted(options.seed),
            selection_mode="multi",
            default=default.seed or None,
            format_func=str,
        )
    module_filter_type: ModuleFilterType | None = st.segmented_control(
        "**Modules Filter Type**",
        options=["Include All", "Include Any"],
        default=default.modules_filter_type,
        help=(
            "When filtering by modules, 'Include All' means the experiment must contain ALL "
            "selected modules. 'Include Any' means the experiment must contain at least one "
            "of the selected modules."
        ),
    )
    if not module_filter_type:
        _ = st.error("Please select a filter type for modules.")
        st.stop()

    filters.modules_filter_type = module_filter_type
    filters.modules = st.pills(
        "**Modules**",
        options=sorted(options.modules),
        selection_mode="multi",
        default=default.modules or None,
        # format_func=titlecase,
    )

    with st.container(horizontal=True, width="content", gap="medium"):
        filters.defuser = st.pills(
            "**Defuser**",
            options=sorted(options.defuser),
            selection_mode="multi",
            default=default.defuser or None,
            width="content",
            format_func=_dummy_model_filter_func,
        )
        filters.expert = st.pills(
            "**Expert**",
            options=sorted(options.expert),
            selection_mode="multi",
            default=default.expert or None,
            format_func=_dummy_model_filter_func,
        )

    with st.container(horizontal=True, width="content", gap="medium"):
        filters.strikes = st.segmented_control(
            "**Strikes**", options=[0, 1, 2], selection_mode="multi"
        )
        filters.outcome = st.segmented_control(
            "**Outcome**", options=["Solved", "Strike Out", "Timeout"], selection_mode="multi"
        )
        filters.time_remaining = st.number_input(
            "Minimum Seconds Remaining",
            min_value=0.0,  # noqa: WPS358
        )

    with st.container(horizontal=True, width="content", gap="medium"):
        filters.tags = st.pills(
            "**Tags**",
            options=sorted(options.tags),
            selection_mode="multi",
            default=default.tags or None,
        )
    return filters


def render_filters(options: Filters, *, expanded: bool = True) -> Filters:
    """Render the filter section with an expander."""
    with st.expander(
        ":small[Filter Experiments]", icon=":material/filter_list:", expanded=expanded
    ):
        _ = st.caption(
            "Select one or more values for each. Empty means no filtering on that attribute."
        )
        with st.container(horizontal=True, width=500):
            name = st.text_input("Name", placeholder="Filter by experiment/attempt name...")

        default = Filters(name=[name] if name else [])

        filters = render_filter_pills(options, default=default)
        return filters
