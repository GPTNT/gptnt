"""Pure data extraction layer for dialogue view."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import structlog
from pydantic_ai.messages import BinaryContent, ModelRequest, UserPromptPart

from gptnt.players.actions import (
    DoNothingAction,
    InteractGameAction,
    LotteryGameAction,
    MagicGameAction,
    PlayerOutputType,
    SendMessageAction,
)

if TYPE_CHECKING:
    from gptnt.players.exceptions import AIResponseErrorType
    from gptnt.players.metrics.records import ExperimentStepRecord


logger = structlog.get_logger()

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


@dataclass
class StepViewModel:
    """Pre-computed view data for a single step.

    This eliminates repeated data extraction during rendering.
    """

    step_idx: int
    step: ExperimentStepRecord
    icon: str
    label: str
    is_defuser: bool
    binary_contents: list[BinaryContent]
    exec_feedbacks: list[str]
    errors: list[AIResponseErrorType]
    usage_summary: str


def build_step_viewmodel(step: ExperimentStepRecord, idx: int) -> StepViewModel:
    """Build a view model for a single step.

    Args:
        step: The step record
        idx: The step index

    Returns:
        Pre-computed StepViewModel
    """
    icon = get_action_icon(cast("type[PlayerOutputType]", type(step.output)))
    label_parts = [f"Step {idx}: {step.player_name} {icon}"]
    if step.is_reflection:
        label_parts.append("🔄")
    if step.error_type:
        label_parts.append("⚠️")
    label = " ".join(label_parts)

    is_defuser = step.role == "defuser"
    binary_contents = extract_binary_content(step)
    exec_feedbacks = extract_nobf_feedback(step)

    usage_summary = (
        f":material/arrow_upward_alt: {step.usage.input_tokens:,} "
        f":material/arrow_downward_alt: {step.usage.output_tokens:,}"
    )

    return StepViewModel(
        step_idx=idx,
        step=step,
        icon=icon,
        label=label,
        is_defuser=is_defuser,
        binary_contents=binary_contents,
        exec_feedbacks=exec_feedbacks,
        errors=step.error_type or [],
        usage_summary=usage_summary,
    )


def build_step_viewmodels(steps: list[ExperimentStepRecord]) -> list[StepViewModel]:
    """Build view models for all steps.

    Args:
        steps: List of step records

    Returns:
        List of pre-computed StepViewModels
    """
    return [build_step_viewmodel(step, idx) for idx, step in enumerate(steps)]
