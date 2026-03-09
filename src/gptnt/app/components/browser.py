import pandas as pd
import streamlit as st

from gptnt.app.app_state import get_state
from gptnt.app.experiment_loader.experiment_selector import render_experiment_selector
from gptnt.app.experiment_loader.scanner import ScannedExperiment


def _select_callback(experiment: ScannedExperiment) -> None:
    state = get_state()
    state.loader.selected_experiment = experiment
    if state.loaded_experiment:
        state.loaded_experiment = None
    _ = st.toast(f"Selected experiment: {experiment.name}")


def render_experiment_browser(
    experiments_to_render: list[ScannedExperiment], entry_render_format: str
) -> None:
    """Render the experiment selection browser."""
    if len(experiments_to_render) > 200:  # noqa: PLR2004
        _ = st.warning(
            f"Too many experiments to display ({len(experiments_to_render)}). "
            "Apply more filters to narrow down the results."
        )

    match entry_render_format:
        case "Cards":
            _ = render_experiment_selector(experiments_to_render, button_callback=_select_callback)
        case "Table":
            df = pd.DataFrame(
                [
                    {
                        "attempt_name": entry.name,
                        "condition": entry.condition,
                        "style": entry.communication_style,
                        "modules": ", ".join(entry.modules) if entry.modules else "",
                        "seed": entry.seed,
                        "defuser": entry.defuser,
                        "expert": entry.expert,
                        "end_state": entry.end_state,
                        "timer": entry.timer_seconds,
                        "strikes": entry.strike_count,
                        "wandb_valid": entry.is_wandb_valid,
                        "tags": ", ".join(entry.tags) if entry.tags else "",
                    }
                    for entry in experiments_to_render
                ]
            )
            _ = st.dataframe(df)
        case _:
            _ = st.error("Unsupported render format selected.")
