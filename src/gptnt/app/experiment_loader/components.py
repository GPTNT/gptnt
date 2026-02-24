import os
from pathlib import Path

import streamlit as st

from gptnt.app.experiment_loader.state import ExperimentLoader


def render_directory_selector(state: ExperimentLoader) -> Path:
    """Render a directory selector for experiment records."""
    data_dir = st.text_input("Experiment Records Directory", value="storage/outputs/custom_outs")
    data_dir_path = Path(data_dir)
    if not data_dir_path.is_dir():
        _ = st.error("Please enter a valid directory path containing experiment records.")
        st.stop()

    state.directory = data_dir_path
    return data_dir_path


def render_wandb_configuration(state: ExperimentLoader) -> None:
    """Render WandB configuration controls in the sidebar."""
    with st.expander(":small[⚙️ WandB Configuration]", expanded=True):
        default_wandb_path = f"{os.getenv('WANDB_ENTITY', '')}/{os.getenv('WANDB_PROJECT', '')}"
        wandb_path = st.text_input("WandB Path", value=default_wandb_path)

        # Update state with wandb config
        state.wandb_path = wandb_path or None

        # Validation toggle
        validate_wandb = st.toggle(
            "Filter invalid experiments with WandB",
            value=False,
            disabled=not wandb_path,
            help="Filter out experiments with invalid wandb runs",
        )
        if not validate_wandb:
            state.wandb_path = None


def render_scan_experiments_controls(
    *, loader: ExperimentLoader, directory: Path, wandb_path: str | None
) -> None:
    """Render controls for scanning experiments and validating with wandb."""
    button_cont = st.container(horizontal=True, gap=None)
    with button_cont:
        button = st.button(
            ":material/feature_search: Scan Experiments",
            type="primary",
            disabled=not directory.is_dir(),
        )
    if button:
        with st.spinner("Scanning experiments..."):
            _, _ = loader.scan(directory=directory, wandb_path=wandb_path)

    with button_cont:
        _ = st.space(size="stretch")
        with st.popover(
            f":small[:material/check: {len(loader.scanned_experiments)} valid]", type="tertiary"
        ):
            for exp in loader.scanned_experiments:
                _ = st.caption(f"{exp.experiment_name}")

    with button_cont:
        _ = st.space(size="stretch")
        with st.popover(
            f":small[:material/warning: {len(loader.invalid_scanned_experiments)} invalid]",
            type="tertiary",
        ):
            for exp in loader.invalid_scanned_experiments:
                _ = st.caption(f"{exp.experiment_name}")
