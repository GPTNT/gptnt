from __future__ import annotations

from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from streamlit.runtime.state import WidgetCallback

    from gptnt.records.models import ExperimentMetadata


STREAMLIT_RED = "#BD4043"
TIMER_COLOR = "#0891B2"
STRIKE_COLOR = "#F59E0B"


def render_selector_legend() -> None:
    """Render legend for experiment selector symbols."""
    with st.popover("Legend", icon=":material/legend_toggle:", type="tertiary"):
        with st.container(gap=None):
            _ = st.caption("Spec")
            _ = st.markdown(":small[:violet[:material/record_voice_over: Communication style]]")
            _ = st.markdown(":small[:green[:material/potted_plant: Seed]]")
            _ = st.markdown(
                '<span style="color: #FA50AC;">:small[:material/call_missed_outgoing: Attempt]</span>',
                unsafe_allow_html=True,
                width="content",
            )
        with st.container(gap=None):
            _ = st.caption("Outcome")
            _ = st.markdown(":small[:blue[:material/crossword: Solved/Total]]", width="content")
            _ = st.markdown(
                f'<span style="color: {TIMER_COLOR};">:small[:material/timer: Time Remaining > 0s]</span> :small[/] <span style="color: {STREAMLIT_RED};">:small[:material/alarm: Time Remaining ≤ 0s]</span>',
                unsafe_allow_html=True,
            )
            _ = st.markdown(
                f'<span style="color: {STRIKE_COLOR};">:small[:material/dangerous: 0-2 Strikes]</span> :small[/] <span style="color: {STREAMLIT_RED};">:small[:material/dangerous: 3+ Strikes]</span>',
                unsafe_allow_html=True,
            )
            _ = st.markdown(":small[:green[:material/celebration: Solved]]")
            _ = st.markdown(":small[:red[:material/destruction: Detonated]]")


def render_experiment_card(  # noqa: WPS231
    experiment: ExperimentMetadata,
    button_callback: WidgetCallback | None = None,
    idx: int | None = None,
    *,
    show_button: bool = True,
) -> ExperimentMetadata | None:
    """Render a single experiment card with selection button."""
    with st.container(gap=None, horizontal=True, height="stretch", border=True, width=375):
        with st.container(gap=None, width=30, height="stretch", vertical_alignment="distribute"):
            if idx is not None:
                _ = st.markdown(f":gray[:small[#{idx + 1}]]")
                _ = st.space(size="stretch")

        with st.container(gap=None, height="stretch"):
            with st.container(horizontal=True, gap="small", width="content"):
                defuser_name = experiment.defuser_name or ""
                if experiment.defuser_has_manual:
                    defuser_name = f"{defuser_name}+:material/book_2:"
                _ = st.markdown(f":small[Defuser: **{defuser_name}**]")
                _ = st.markdown(f":small[Expert: **{experiment.expert_name!s}**]")
            with st.container(horizontal=True, gap=None, width="content"):
                _ = st.markdown(f":small[Modules: **{', '.join(experiment.modules_str or [])}**]")
            for tag in experiment.tags or []:
                _ = st.badge(tag, color="red")
            with st.container(gap="xsmall", horizontal=True):
                _ = st.markdown(
                    f":small[:violet[:material/record_voice_over: {(experiment.communication_style or '').title()}]]",
                    width="content",
                )
                _ = st.markdown(
                    f":small[:green[:material/potted_plant: {experiment.seed}]]", width="content"
                )
                _ = st.markdown(
                    f'<span style="color: #FA50AC;">:small[:material/call_missed_outgoing: {experiment.attempt}]</span>',
                    unsafe_allow_html=True,
                    width="content",
                )
                _ = st.markdown(
                    f":small[:blue[:material/crossword: {experiment.num_modules_solved}/{len(experiment.modules or [])}]]",
                    width="content",
                )
                timer_color = TIMER_COLOR
                timer_icon = ":material/timer:"
                if experiment.seconds_remaining <= 0:
                    timer_color = STREAMLIT_RED
                    timer_icon = ":material/alarm:"
                _ = st.markdown(
                    f'<span style="color: {timer_color};">:small[{timer_icon} {experiment.seconds_remaining:.1f}s]</span>',
                    unsafe_allow_html=True,
                    width="content",
                )
                strike_color = STRIKE_COLOR
                if experiment.strike_count >= 3:  # noqa: PLR2004
                    strike_color = STREAMLIT_RED
                _ = st.markdown(
                    f'<span style="color: {strike_color};">:small[:material/dangerous: {experiment.strike_count}]</span>',
                    unsafe_allow_html=True,
                    width="content",
                )
                if experiment.is_solved:
                    _ = st.markdown(":small[:green[:material/celebration:]]")
                if experiment.is_detonated:
                    _ = st.markdown(":small[:red[:material/destruction:]]")

        if show_button:
            with st.container(
                gap=None, width=20, height="stretch", vertical_alignment="distribute"
            ):
                button = st.button(
                    "",
                    key=f"select_{experiment.attempt_name}",
                    icon=":material/play_circle:",
                    type="tertiary",
                    on_click=button_callback,
                    args=(experiment,) if button_callback else None,
                )

            if button:
                return experiment

    return None
