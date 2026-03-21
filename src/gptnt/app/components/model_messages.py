import io
import itertools
from typing import cast

import streamlit as st
from htbuilder import div, styles
from htbuilder.units import rem
from PIL import Image
from pydantic_ai import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from gptnt.records.models import ExperimentStepRecord


def render_image_gallery(
    binary_contents: list[BinaryContent], *, num_cols_multi: int = 3, num_cols_single: int = 2
) -> None:
    """Render images from BinaryContent objects in a grid.

    Args:
        binary_contents: List of BinaryContent objects to render
        num_cols_multi: Number of columns for multiple images
        num_cols_single: Number of columns for single image
    """
    if not binary_contents:
        return

    num_cols = num_cols_single if len(binary_contents) == 1 else num_cols_multi

    with st.expander(
        f":small[Observations sent to model ({len(binary_contents)})]",
        icon=":material/animated_images:",
        expanded=False,
    ):
        cols = st.columns(num_cols)

        for idx, binary_content in enumerate(binary_contents):
            col_idx = idx % num_cols
            with cols[col_idx]:
                img = Image.open(io.BytesIO(binary_content.data))
                _ = st.image(img, width="stretch")


def render_model_instructions(all_messages: list[ModelMessage]) -> None:
    """Render the instructions given to the model in a dialog."""
    # First, find and render the model instructions, they'll be there somewhere
    any_request = next(
        (
            msg
            for msg in all_messages
            if isinstance(msg, ModelRequest) and msg.instructions is not None
        ),
        None,
    )

    # Only show the instructions for the first message as they are all the same.
    if not any_request or not any_request.instructions:
        return

    with st.expander("📜 :small[Model instructions]", expanded=False):
        output_format = st.segmented_control(
            "Format",
            ["Pretty", "Raw"],
            selection_mode="single",
            default="Pretty",
            label_visibility="collapsed",
        )
        match output_format:
            case "Pretty":
                _ = st.markdown(any_request.instructions)
            case "Raw":
                _ = st.code(
                    any_request.instructions,
                    language="markdown",
                    wrap_lines=True,
                    line_numbers=True,
                )
            case _:
                return


def render_user_prompts(parts: list[UserPromptPart], *, is_expanded: bool = False) -> None:  # noqa: WPS231
    """Render user prompt parts."""
    if not parts:
        return

    # First, parse the content into a flat list of strings and BinaryContent for easier rendering
    parsed_content: list[str | BinaryContent] = []
    for part in parts:
        if isinstance(part.content, str):
            parsed_content.append(part.content)
        elif isinstance(part.content, list):
            for chunk in part.content:
                if isinstance(chunk, (str, BinaryContent)):
                    parsed_content.append(chunk)  # noqa: PERF401

    # Group consecutive BinaryContent together for gallery rendering, and strings together for code
    # block rendering
    grouped_list = itertools.groupby(
        parsed_content, key=lambda content: isinstance(content, BinaryContent)
    )

    # Now render
    with st.expander(":small[Request]", expanded=is_expanded):
        for is_binary, part_group in grouped_list:
            part_list = list(part_group)
            if is_binary:
                render_image_gallery(cast("list[BinaryContent]", part_list))
            else:
                _ = st.code(
                    "\n".join(cast("list[str]", part_list)), language="markdown", wrap_lines=True
                )


def render_model_response(msg: ModelResponse, *, is_expanded: bool = False) -> None:
    """Render a ModelResponse message."""
    all_text_parts = [part for part in msg.parts if isinstance(part, TextPart)]

    with st.expander(":small[Response]", expanded=is_expanded):
        for text_part in all_text_parts:
            _ = st.code(text_part.content, language="markdown", wrap_lines=True)


def render_small_html_text(text: str) -> None:
    """Render small HTML text."""
    small_text = div(style=styles(font_size=rem(0.8), line_height=1.2))(text)
    _ = st.html(small_text)


def render_thoughts(thoughts: str) -> None:
    """Render the model's thoughts in an expander."""
    with st.expander(":small[Thoughts]", icon=":material/neurology:", expanded=False):
        render_small_html_text(thoughts)


@st.dialog("Messages for this step", width="medium")
def render_messages_modal(step: ExperimentStepRecord) -> None:
    """Render a dialog showing input and new messages for this step."""
    all_messages = list(itertools.chain(step.input_messages, step.new_messages))

    render_model_instructions(all_messages)

    for msg_idx, message in enumerate(all_messages):
        if isinstance(message, ModelRequest):
            user_parts = [part for part in message.parts if isinstance(part, UserPromptPart)]
            render_user_prompts(user_parts, is_expanded=(msg_idx >= len(all_messages) - 2))
        else:
            render_model_response(message, is_expanded=(msg_idx >= len(all_messages) - 1))

    if not step.input_messages and not step.new_messages:
        _ = st.warning("No messages recorded for this step")
