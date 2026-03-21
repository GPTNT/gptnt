import io
import re
from typing import cast

import streamlit as st
from PIL import Image, ImageDraw
from pydantic_ai import BinaryContent, ModelRequest, UserPromptPart

from gptnt.app.components.model_messages import (
    render_image_gallery,
    render_messages_modal,
    render_small_html_text,
    render_thoughts,
)
from gptnt.ktane.actions import RelativeCoordinate
from gptnt.players.actions import (
    DoNothingAction,
    InteractGameAction,
    LotteryGameAction,
    MagicGameAction,
    PlayerOutputType,
    SendMessageAction,
)
from gptnt.players.exceptions import AIResponseErrorType
from gptnt.players.observation_handler import Observation
from gptnt.records.models import ExperimentStepRecord

EXEC_FEEDBACK_RE = re.compile(r"<execution-feedback>(.*?)</execution-feedback>", re.DOTALL)


ACTION_ICONS: dict[type[PlayerOutputType], str] = {  # noqa: WPS407
    SendMessageAction: "💬",
    InteractGameAction: "🎮",
    DoNothingAction: "⏸",
    MagicGameAction: "✨",
    LotteryGameAction: "🍀",
}


def _flatten_user_prompt_part(part: UserPromptPart) -> str:
    """Flatten a UserPromptPart into a string."""
    all_text = []
    if isinstance(part.content, str):
        all_text.append(part.content)
    elif isinstance(part.content, list):
        for chunk in part.content:
            if isinstance(chunk, str):
                all_text.append(chunk)  # noqa: PERF401

    return "\n".join(all_text)


def extract_nobf_feedback(step: ExperimentStepRecord) -> list[str]:
    """Pull all the NOBF from the step."""
    feedback: list[str] = []
    for msg in step.new_messages:
        if not isinstance(msg, ModelRequest):
            continue
        all_text: list[str] = [
            _flatten_user_prompt_part(part)
            for part in msg.parts
            if isinstance(part, UserPromptPart)
        ]

        text = "\n".join(all_text)
        feedback.extend(EXEC_FEEDBACK_RE.findall(text))

    return feedback


def extract_binary_content(step: ExperimentStepRecord) -> list[BinaryContent]:  # noqa: WPS231
    """Extract all BinaryContent (images) from the step's new messages.

    These are the actual images sent to the model in this step.
    """
    binary_contents: list[BinaryContent] = []

    for msg in step.new_messages:
        if not isinstance(msg, ModelRequest):
            continue

        for part in msg.parts:
            if isinstance(part, UserPromptPart) and isinstance(part.content, list):
                binary_contents.extend(
                    content for content in part.content if isinstance(content, BinaryContent)
                )
    return binary_contents


def get_action_icon(output_type: type[PlayerOutputType]) -> str:
    """Get the icon for an action output type."""
    output_handler = next(
        ACTION_ICONS[output_class]
        for output_class in output_type.__mro__
        if output_class in ACTION_ICONS
    )
    return output_handler


def get_step_label(step: ExperimentStepRecord, idx: int) -> str:
    """Build the display label for a step."""
    icon = get_action_icon(cast("type[PlayerOutputType]", type(step.output)))
    parts = [f"Step {idx}: {step.player_name} {icon}"]
    if step.is_reflection:
        parts.append("🔄")
    if step.error_type:
        parts.append("⚠️")
    return " ".join(parts)


def get_usage_summary(step: ExperimentStepRecord) -> str:
    """Format token usage as a display string."""
    return (
        f":material/arrow_upward_alt: {step.usage.input_tokens:,} "
        f":material/arrow_downward_alt: {step.usage.output_tokens:,}"
    )


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
    step: ExperimentStepRecord, idx: int, *, render_as_raw: bool, force_collapsed: bool
) -> None:
    """Render a single dialogue bubble for a step."""
    if step.role == "defuser":
        msg_col, _ = st.columns([5, 1])
    else:
        _, msg_col = st.columns([1, 5])

    label = get_step_label(step, idx)
    errors = step.error_type or []
    exec_feedbacks = extract_nobf_feedback(step)
    binary_contents = extract_binary_content(step)

    with msg_col, st.expander(label=label, expanded=not force_collapsed):
        if exec_feedbacks:
            render_nobf_output(exec_feedbacks)

        if binary_contents:
            render_image_gallery(binary_contents)

        render_action_output(step, render_as_raw=render_as_raw)

        with st.container(horizontal=True, vertical_alignment="center"):
            _ = st.caption(get_usage_summary(step), width="content")
            if step.bomb_state:
                _ = st.caption(
                    f":material/timer: {step.bomb_state.timer_module.seconds_remaining:.1f}s",
                    width="content",
                )
                _ = st.caption(
                    f":material/disabled_by_default: {len(step.bomb_state.strikes) if step.bomb_state.strikes else 0} strikes",
                    width="content",
                )

            render_response_errors(errors)
            _ = st.space(size="stretch")
            render_popover_for_click_location(step)

            if st.button(
                ":small[:gray[:material/code_blocks: Raw messages]]",
                type="secondary",
                key=f"view_msgs_{idx}",
                help="View the raw messages sent to and from the model for this step",
            ):
                render_messages_modal(step)
