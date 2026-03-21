from dataclasses import dataclass

import structlog
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

logger = structlog.get_logger()


@dataclass(kw_only=True)
class SingleRun:
    """Hold the messages for a single model run."""

    messages: list[ModelMessage]

    idx: int
    contains_manual: bool

    input_tokens: int
    output_tokens: int

    @property
    def contains_binary_content(self) -> bool:  # noqa: WPS231
        """Check if the messages contain any observations."""
        for message in self.messages:
            if isinstance(message, ModelRequest):
                for part in message.parts:
                    part_has_binary_content = (
                        isinstance(part, UserPromptPart)
                        and not isinstance(part.content, str)
                        and any(isinstance(content, BinaryContent) for content in part.content)
                    )
                    if part_has_binary_content:
                        return True  # noqa: WPS220
        return False
