from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Self, get_args, override

import streamlit as st
import yaml
from caseconverter import titlecase
from more_itertools import flatten

from gptnt.common.paths import Paths
from gptnt.experiments.db.connection import DuckDBConnection
from gptnt.experiments.models import ExperimentSummary
from gptnt.experiments.spec import Condition
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.specification import CommunicationStyle

type ModuleFilterType = Literal["Include All", "Include Any"]
type OutcomeType = Literal["Solved", "Strike Out", "Timeout"]


@st.cache_data()
def _load_available_players() -> list[str]:
    player_names = []
    for model_file in Paths().model_configs.glob("*.yaml"):
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
    attempt_name: Sequence[str] = field(default_factory=list)
    strikes: Sequence[int] = field(default_factory=list)
    outcome: Sequence[OutcomeType] = field(default_factory=list)
    tags: Sequence[str] = field(default_factory=list)
    modules_filter_type: ModuleFilterType = field(default="Include All")
    seconds_remaining: float = field(default=0)
    defuser_has_manual: bool | None = field(default=None)

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
                tuple(self.attempt_name),
                tuple(self.strikes),
                tuple(self.outcome),
                tuple(self.tags),
                self.modules_filter_type,
                self.seconds_remaining,
                self.defuser_has_manual,
            )
        )

    @classmethod
    def from_experiments(cls, experiments: list[ExperimentSummary]) -> Self:
        """Derive available filter options from a list of scanned experiments.

        Uses the full set of valid conditions, communication styles, and modules from the type
        definitions, and derives defusers, experts, and seeds from the actual scanned data.
        """
        if experiments:
            defuser = sorted({exp.defuser_name for exp in experiments if exp.defuser_name})
            expert = sorted({exp.expert_name for exp in experiments if exp.expert_name})
            seed = sorted({exp.seed for exp in experiments if exp.seed})
        else:
            defuser = ALL_PLAYERS
            expert = [*ALL_PLAYERS, "None"]
            seed = []
        return cls(
            condition=ALL_CONDITIONS,
            communication_style=ALL_COMMUNICATION_STYLES,
            modules=ALL_MODULES,
            defuser=defuser,
            expert=expert,
            seed=seed,
            modules_filter_type="Include All",
            attempt_name=[exp.attempt_name for exp in experiments],
            tags=list(set(flatten(exp.tags for exp in experiments if exp.tags))),
        )


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

    with st.container(horizontal=True, width="content"):
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
        if module_filter_type is None:
            _ = st.error("Please select a filter type for modules.")
            st.stop()
        filters.modules_filter_type = module_filter_type

        filters.defuser_has_manual = st.segmented_control(
            "**Defuser Has Manual**", options=[False, True], selection_mode="single", default=None
        )

    filters.modules = st.pills(
        "**Modules**",
        options=sorted(options.modules),
        selection_mode="multi",
        default=default.modules or None,
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
        filters.seconds_remaining = st.number_input(
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

        default = Filters(attempt_name=[name] if name else [])

        filters = render_filter_pills(options, default=default)
        return filters


def distinct[OutT](conn: DuckDBConnection, col: str) -> list[OutT]:
    """Fetch distinct non-null values for a scalar column."""
    return [
        row[0]
        for row in conn.execute(
            f"SELECT DISTINCT {col} FROM experiment_summary ORDER BY {col}"  # noqa: S608
        ).fetchall()
    ]


def distinct_unnested[OutT](conn: DuckDBConnection, col: str) -> list[OutT]:
    """Fetch distinct values from an array column via DuckDB's unnest."""
    return [
        row[0]
        for row in conn.execute(
            f"SELECT DISTINCT unnest({col}) AS val FROM experiment_summary ORDER BY val"  # noqa: S608
        ).fetchall()
    ]


def load_options_for_filters(connection: DuckDBConnection) -> Filters:
    """Load the options for the filters from the database."""
    return Filters(
        condition=distinct(connection, "condition"),
        communication_style=distinct(connection, "communication_style"),
        modules=distinct_unnested(connection, "modules"),
        defuser=distinct(connection, "defuser_name"),
        expert=list(map(str, distinct(connection, "expert_name"))),
        seed=distinct(connection, "seed"),
        attempt_name=distinct(connection, "attempt_name"),
        tags=distinct_unnested(connection, "tags"),
    )


OUTCOME_SQL: dict[OutcomeType, str] = {  # noqa: WPS407
    "Solved": "is_solved = true",
    "Strike Out": "is_strike_out = true",
    "Timeout": "is_timed_out = true",
}


def _build_sql_filters(filters: Filters) -> tuple[str, list[Any]]:  # noqa: PLR0912, WPS210, WPS213, WPS231
    """Translate a Filters object into a parameterised SQL WHERE clause."""
    clauses: list[str] = []
    params: list[Any] = []

    for col, col_values in (
        ("condition", filters.condition),
        ("communication_style", filters.communication_style),
        ("defuser_name", filters.defuser),
        ("seed", filters.seed),
        ("strike_count", filters.strikes),
    ):
        if col_values:
            placeholders = ", ".join("?" * len(col_values))
            clauses.append(f"{col} IN ({placeholders})")
            params.extend(col_values)

    # We do the expert separately because it can be none
    if filters.expert:
        real_experts = [e for e in filters.expert if e != "None"]  # noqa: WPS111
        include_null = len(real_experts) < len(list(filters.expert))

        parts: list[str] = []
        if real_experts:
            placeholders = ", ".join("?" * len(real_experts))
            parts.append(f"expert_name IN ({placeholders})")
            params.extend(real_experts)
        if include_null:
            parts.append("expert_name IS NULL")
        clauses.append(f"({' OR '.join(parts)})")

    if filters.modules:
        fn = "list_has_all" if filters.modules_filter_type == "Include All" else "list_has_any"
        clauses.append(f"{fn}(modules, ?)")
        params.append(list(filters.modules))

    if filters.tags:
        clauses.append("list_has_any(tags, ?)")
        params.append(list(filters.tags))

    for part in filters.attempt_name:
        clauses.append("lower(attempt_name) LIKE ?")
        params.append(f"%{part.lower()}%")

    if filters.seconds_remaining > 0:
        clauses.append("seconds_remaining >= ?")
        params.append(filters.seconds_remaining)

    if filters.defuser_has_manual is True:
        clauses.append("pairing LIKE '%+manual%'")
    elif filters.defuser_has_manual is False:
        clauses.append("(pairing IS NULL OR pairing NOT LIKE '%+manual%')")

    active = [OUTCOME_SQL[key] for key in filters.outcome if key in OUTCOME_SQL]
    if active:
        clauses.append(f"({' OR '.join(active)})")

    where = ""
    if clauses:
        where = f"WHERE {' AND '.join(clauses)}"
    return where, params


def apply_filters(connection: DuckDBConnection, filters: Filters) -> list[ExperimentSummary]:
    """Fetch experiments from DuckDB with all filters applied server-side."""
    where, params = _build_sql_filters(filters)
    output = connection.execute(f"SELECT * FROM {ExperimentSummary.table_name()} {where}", params)  # noqa: S608

    col_names = [desc[0] for desc in output.description]
    return [
        ExperimentSummary.model_validate(dict(zip(col_names, row, strict=False)))
        for row in output.fetchall()
    ]
