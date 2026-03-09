"""Experiment summary header with clean, functional design."""

from __future__ import annotations

from typing import TYPE_CHECKING

import st_tailwind as tw
import streamlit as st
from caseconverter import titlecase
from htbuilder import div, styles
from htbuilder.units import rem
from whenever import seconds

from gptnt.players.actions import SendMessageAction

if TYPE_CHECKING:
    from gptnt.players.metrics.records import ExperimentRecord, ExperimentStepRecord
    from gptnt.players.specification import PlayerProtocol


def _render_strikes(current: int, max_strikes: int) -> None:
    """Render strikes with color coding."""
    color = "red" if current >= max_strikes else ""
    strikes_formatted = f"**{current} / {max_strikes}**"
    if color:
        strikes_formatted = f":{color}[{strikes_formatted}]"
    _ = st.markdown(strikes_formatted)


def _render_time_progress(seconds_remaining: float, total_seconds: float) -> None:
    # show as MM:SS if more than 60 seconds
    _, remaining_minutes, remaining_seconds, _ = (
        seconds(seconds_remaining).round("second").in_hrs_mins_secs_nanos()
    )
    color = "red" if seconds_remaining <= 0 else ""
    remaining_time_formatted = f"{remaining_minutes:02d}:{remaining_seconds:02d}"
    if color:
        remaining_time_formatted = f":{color}[{remaining_time_formatted}]"

    _, total_minutes, total_seconds, _ = (
        seconds(total_seconds).round("second").in_hrs_mins_secs_nanos()
    )
    total_time_formatted = f"{total_minutes:02d}:{total_seconds:02d}"

    _ = st.markdown(
        f"**{remaining_time_formatted}**  &nbsp;&nbsp;&nbsp;:small[:gray[(/{total_time_formatted})]]"
    )


def render_experiment_progress(experiment_record: ExperimentRecord) -> None:  # noqa: WPS210
    """Render experiment progress and outcome."""
    bomb_state = next(
        (
            step.bomb_state
            for step in reversed(experiment_record.step_records)
            if step.bomb_state is not None
        ),
        None,
    )
    if bomb_state is None:
        _ = st.markdown("**Experiment has no recorded bomb state.**")
        return
    # Show strikes, timer progress, modules solved, final result as "strike out", "timed out", or "solved"
    columns = st.columns([1, 1], gap=None)
    _ = columns[0].caption("Strikes")
    with columns[1]:
        _render_strikes(bomb_state.current_strikes, bomb_state.max_strikes)
    columns = st.columns([1, 1], gap=None)
    _ = columns[0].caption("Time Left")
    with columns[1]:
        _render_time_progress(
            bomb_state.timer_module.seconds_remaining,
            experiment_record.experiment_descriptor.experiment_spec.mission_spec.time_limit,
        )
    columns = st.columns([1, 1], gap=None)
    _ = columns[0].caption("Modules Solved")
    _ = columns[1].markdown(
        f"**{sum(1 for module in bomb_state.modules if module.is_solved)} / {len(bomb_state.modules)}**"
    )


def _render_player_card(
    name: str, protocol: PlayerProtocol, role: str, reflection: ExperimentStepRecord | None = None
) -> None:
    """Render a single player info card."""
    icon = (
        ":material/document_search:"
        if role == "Expert"
        else ":material/tools_pliers_wire_stripper:"
    )

    with tw.container(border=True, gap=None):
        _ = st.markdown(f"**{icon} {role}** — {titlecase(name)}")
        _ = st.space()
        details = {
            "Manual Access": ":material/check:" if protocol.include_manual else ":material/close:",
            "TAPF Feedback": ":material/check:"
            if protocol.receive_feedback_after_action
            else ":material/close:",
            "Magic Actions": ":material/check:"
            if protocol.allow_magic_actions
            else ":material/close:",
        }
        with st.container(gap=None):
            for label, checkmark in details.items():
                cols = st.columns([1, 1])
                with cols[0]:
                    _ = st.caption(label)
                with cols[1]:
                    _ = st.markdown(checkmark)

        with st.popover(":small[Reflection]", icon=":material/clinical_notes:", type="tertiary"):
            if reflection:
                thoughts_render = div(
                    style=styles(font_size=rem(0.9), font_style="italic", line_height=1.4)
                )(
                    reflection.thoughts
                    if reflection.thoughts
                    else "(No thoughts recorded for this reflection.)"
                )
                _ = st.html(thoughts_render)
                _ = st.markdown(
                    reflection.output.message
                    if isinstance(reflection.output, SendMessageAction)
                    else "No message output in reflection step."
                )


def render_player_cards(experiment_record: ExperimentRecord) -> None:
    """Render player cards side by side."""
    # Try to get the reflection out the playher records if they exist
    defuser_reflection = next(
        (
            step
            for player_record in experiment_record.player_records
            if player_record.role == "defuser"
            for step in reversed(player_record.step_records)
            if step.is_reflection
        ),
        None,
    )
    expert_reflection = next(
        (
            step
            for player_record in experiment_record.player_records
            if player_record.role == "expert"
            for step in reversed(player_record.step_records)
            if step.is_reflection
        ),
        None,
    )

    spec = experiment_record.experiment_descriptor.experiment_spec
    if spec.expert_name and spec.expert_protocol:
        cols = st.columns(2)
        with cols[0]:
            _render_player_card(
                spec.defuser_name, spec.defuser_protocol, "Defuser", reflection=defuser_reflection
            )
        with cols[1]:
            _render_player_card(
                spec.expert_name, spec.expert_protocol, "Expert", reflection=expert_reflection
            )
    else:
        _render_player_card(
            spec.defuser_name, spec.defuser_protocol, "Defuser", reflection=defuser_reflection
        )


def render_experiment_summary_header(experiment_record: ExperimentRecord) -> None:
    """Render clean, functional experiment summary header.

    Displays experiment metadata, outcome, bomb state, players, and performance metrics in a clear,
    hierarchical layout.
    """
    with st.container(border=True, gap=None):
        _ = tw.markdown(":gray[Outcome]")
        _ = st.space()
        render_experiment_progress(experiment_record)
