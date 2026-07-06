import st_tailwind as tw
import streamlit as st
from caseconverter import titlecase
from htbuilder import div, styles
from htbuilder.units import rem

from gptnt.experiments.models import ExperimentRecord, ExperimentStep
from gptnt.players.actions import SendMessageAction
from gptnt.players.specification import PlayerProtocol


def render_player_card(
    name: str, protocol: PlayerProtocol, role: str, reflection: ExperimentStep | None = None
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
                )(reflection.thoughts or "(No thoughts recorded for this reflection.)")
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
            render_player_card(
                spec.defuser_name, spec.defuser_protocol, "Defuser", reflection=defuser_reflection
            )
        with cols[1]:
            render_player_card(
                spec.expert_name, spec.expert_protocol, "Expert", reflection=expert_reflection
            )
    else:
        render_player_card(
            spec.defuser_name, spec.defuser_protocol, "Defuser", reflection=defuser_reflection
        )
