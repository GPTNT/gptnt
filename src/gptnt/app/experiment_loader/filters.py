from pathlib import Path
from typing import get_args

import streamlit as st
import yaml

from gptnt.app.components.filter_pills import Filters
from gptnt.app.experiment_loader.scanner import ScannedExperiment
from gptnt.experiments.experiments import Condition
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.players.specification import CommunicationStyle


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
ALL_MODULES = sorted(set(KtaneComponent.__members__.keys()))
ALL_PLAYERS = _load_available_players()


def get_filter_options(scanned_experiments: list[ScannedExperiment]) -> Filters:
    """Derive available filter options from a list of scanned experiments.

    Uses the full set of valid conditions, communication styles, and modules from the type
    definitions, and derives defusers, experts, and seeds from the actual scanned data.
    """
    return Filters(
        condition=ALL_CONDITIONS,
        communication_style=ALL_COMMUNICATION_STYLES,
        modules=sorted({mod for exp in scanned_experiments for mod in exp.modules}),
        defuser=sorted({exp.defuser for exp in scanned_experiments if exp.defuser}),
        expert=sorted({exp.expert for exp in scanned_experiments if exp.expert}),
        seed=sorted({exp.seed for exp in scanned_experiments if exp.seed}),
        modules_filter_type="Include All",
    )


def apply_filters(
    scanned_experiments: list[ScannedExperiment], filters: Filters
) -> list[ScannedExperiment]:
    """Apply filters to scanned experiments."""
    filtered = scanned_experiments

    if filters.condition:
        filtered = [exp for exp in filtered if exp.condition in filters.condition]

    if filters.communication_style:
        filtered = [
            exp for exp in filtered if exp.communication_style in filters.communication_style
        ]

    if filters.modules:
        if filters.modules_filter_type == "Include All":
            selected_modules = set(filters.modules)
            filtered = [exp for exp in filtered if selected_modules.issubset(set(exp.modules))]
        else:  # Include Any
            selected_modules = set(filters.modules)
            filtered = [exp for exp in filtered if selected_modules.intersection(set(exp.modules))]

    if filters.defuser:
        filtered = [exp for exp in filtered if exp.defuser in filters.defuser]

    if filters.expert:
        filtered = [exp for exp in filtered if exp.expert in filters.expert]

    if filters.seed:
        filtered = [exp for exp in filtered if exp.seed in filters.seed]

    return filtered
