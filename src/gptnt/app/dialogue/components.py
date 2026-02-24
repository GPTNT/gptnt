from __future__ import annotations

import io
import itertools
from typing import TYPE_CHECKING

import streamlit as st
from PIL import Image, ImageDraw
from pydantic_ai import ModelRequest, UserPromptPart

from gptnt.app.components.model_messages import (
    render_image_gallery,
    render_model_instructions,
    render_model_response,
    render_small_html_text,
    render_thoughts,
    render_user_prompts,
)
from gptnt.app.dialogue.state import PAGE_SIZE_OPTIONS
from gptnt.ktane.actions import RelativeCoordinate
from gptnt.players.actions import (
    DoNothingAction,
    InteractGameAction,
    MagicGameAction,
    SendMessageAction,
)
from gptnt.players.observation_handler import Observation

if TYPE_CHECKING:
    from collections.abc import Iterable

    from gptnt.app.dialogue.data import StepViewModel
    from gptnt.app.dialogue.state import DialogueState, PaginationInfo
    from gptnt.players.exceptions import AIResponseErrorType
    from gptnt.players.metrics.records import ExperimentStepRecord


@st.dialog("Messages for this step", width="medium")
def render_messages_modal(vm: StepViewModel) -> None:
    """Render a dialog showing input and new messages for this step."""
    step = vm.step

    all_messages = list(itertools.chain(step.input_messages, step.new_messages))

    render_model_instructions(all_messages)

    for idx, message in enumerate(all_messages):
        if isinstance(message, ModelRequest):
            user_parts = [part for part in message.parts if isinstance(part, UserPromptPart)]
            render_user_prompts(user_parts, is_expanded=(idx >= len(all_messages) - 2))
        else:
            render_model_response(message, is_expanded=(idx >= len(all_messages) - 1))

    if not step.input_messages and not step.new_messages:
        _ = st.warning("No messages recorded for this step")


def render_action_output(step: ExperimentStepRecord, *, render_as_raw: bool) -> None:  # noqa: WPS231
    """Render the action output for a step."""
    # Show raw output if requested (which does include the thoughts)
    if render_as_raw:
        _ = st.code(
            step.raw_output or "(no raw output recorded)", language="markdown", wrap_lines=True
        )
        return

    # Show thoughts if present and not in raw mode
    if step.thoughts and not render_as_raw:
        render_thoughts(step.thoughts)

    # Format output based on type
    if isinstance(step.output, SendMessageAction):
        _ = st.markdown(step.output.message)
    elif isinstance(step.output, InteractGameAction):
        loc = getattr(step.output, "location", None)
        if loc:
            _ = st.code(f"🎮 {step.output.action.value} @ {loc}", language=None)
        else:
            _ = st.code(f"🎮 {step.output.action.value}", language=None)
    elif isinstance(step.output, DoNothingAction):
        _ = st.caption("⏸ _Waiting — no action_")
    elif isinstance(step.output, MagicGameAction):
        _ = st.caption("✨ _Magic action_")
    else:
        _ = st.code(str(step.output), language=None)


def render_popover_for_click_location(step: ExperimentStepRecord) -> None:
    """Conditionally, render a popover showing the click location."""
    if (
        isinstance(step.output, InteractGameAction)
        and hasattr(step.output, "location")
        and isinstance(step.output.location, RelativeCoordinate)
        and isinstance(step.observation, Observation)
    ):
        with st.popover(":small[:gray[:material/left_click: Click location]]"):
            render_click_location_on_image(
                step.observation.som_image, step.output.location.x_pos, step.output.location.y_pos
            )


def render_click_location_on_image(image: bytes, x_pos: float, y_pos: float) -> None:
    """Show the click location on the image."""
    img = Image.open(io.BytesIO(image))
    img_width, img_height = img.size
    click_x = int(x_pos * img_width)
    click_y = int(y_pos * img_height)

    # Create a copy of the image to draw on
    img_with_click = img.copy()
    draw = ImageDraw.Draw(img_with_click)
    radius = 10
    draw.ellipse(
        (click_x - radius, click_y - radius, click_x + radius, click_y + radius),
        fill=(255, 0, 0, 100),
        outline="white",
        width=2,
    )

    _ = st.image(img_with_click, width="stretch")


def render_nobf_output(nobf_output: list[str]) -> None:
    """Render additional NOBF output."""
    with st.expander(":small[NOBF]", icon=":material/sentiment_sad:", expanded=False):
        for fb in nobf_output:
            render_small_html_text(fb.strip())


def render_response_errors(errors: list[AIResponseErrorType] | None) -> None:
    """Render any errors that occurred during the model response."""
    if errors:
        with st.popover(":small[:red[Errors]]", type="tertiary"):
            _ = st.markdown("**Errors during model response:**")
            for error in errors:
                _ = st.markdown(f"- `{error.value}`")


def render_dialogue_bubble(
    vm: StepViewModel, *, render_as_raw: bool, force_collapsed: bool
) -> None:
    """Render a single dialogue bubble for a step."""
    # Left / right alignment via columns
    if vm.is_defuser:
        msg_col, _ = st.columns([5, 1])
    else:
        _, msg_col = st.columns([1, 5])

    with msg_col, st.expander(label=vm.label, expanded=not force_collapsed):
        if vm.exec_feedbacks:
            render_nobf_output(vm.exec_feedbacks)

        if vm.binary_contents:
            render_image_gallery(vm.binary_contents)

        render_action_output(vm.step, render_as_raw=render_as_raw)

        # Token counter footer and messages button
        with st.container(horizontal=True, vertical_alignment="center"):
            _ = st.caption(vm.usage_summary, width="content")
            if vm.step.bomb_state:
                _ = st.caption(
                    f":material/timer: {vm.step.bomb_state.timer_module.seconds_remaining:.1f}s",
                    width="content",
                )
                _ = st.caption(
                    f":material/disabled_by_default: {len(vm.step.bomb_state.strikes) if vm.step.bomb_state.strikes else 0} strikes",
                    width="content",
                )

            render_response_errors(vm.errors)
            _ = st.space(size="stretch")
            render_popover_for_click_location(vm.step)

            if st.button(
                ":small[:gray[:material/code_blocks: Raw messages]]",
                type="secondary",
                key=f"view_msgs_{vm.step_idx}",
                help="View the raw messages sent to and from the model for this step",
            ):
                render_messages_modal(vm)


def render_display_controls(
    state: DialogueState, *, page_size_options: Iterable[int] = PAGE_SIZE_OPTIONS
) -> tuple[str, str, int]:
    """Render display control selectors."""
    with st.container(horizontal=True, vertical_alignment="center"):
        output_format = st.segmented_control(
            "Output Format",
            ["Pretty", "Raw"],
            selection_mode="single",
            default=state.output_format,
        )
        _ = st.space(size="stretch")
        message_display = st.segmented_control(
            "Message Display",
            ["Expanded", "Folded"],
            selection_mode="single",
            default=state.message_display,
        )

        _ = st.space(size="stretch")
        page_size = st.segmented_control(
            "Steps per page",
            options=page_size_options,
            key="page_size_selector",
            default=state.page_size,
        )
    return output_format or "Pretty", message_display or "Expanded", page_size or state.page_size


def render_pagination_controls(
    pagination: PaginationInfo, state: DialogueState, key_suffix: str
) -> None:
    """Render pagination navigation controls.

    Args:
        pagination: PaginationInfo with current pagination state
        state: DialogueState for navigation actions
        key_suffix: Suffix for unique widget keys (e.g., "top" or "bottom")
    """
    if pagination.total_pages <= 1:
        return

    nav_cols = st.columns([1, 3, 1])

    with nav_cols[0]:
        if st.button(
            ":material/chevron_left: Previous",
            disabled=not pagination.has_prev,
            width="stretch",
            key=f"prev_{key_suffix}",
        ):
            state.go_prev()

    with nav_cols[1]:
        if key_suffix == "top":
            info_text = (
                f"<div style='text-align: center'>Page {pagination.current_page + 1} "
                f"of {pagination.total_pages} | "
                f"Showing steps {pagination.start_idx + 1}-{pagination.end_idx} "
                f"of {pagination.total_items}</div>"
            )
        else:
            info_text = (
                f"<div style='text-align: center'>Page {pagination.current_page + 1} "
                f"of {pagination.total_pages}</div>"
            )
        _ = st.markdown(info_text, unsafe_allow_html=True)

    with nav_cols[2]:
        if st.button(
            "Next :material/chevron_right:",
            disabled=not pagination.has_next,
            width="stretch",
            key=f"next_{key_suffix}",
        ):
            state.go_next(pagination.total_pages)
