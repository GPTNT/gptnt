from pydantic_ai import ModelMessage, ModelResponse, TextPart, ThinkingPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from gptnt.players.actions import PlayerOutputType
from gptnt.players.reasoning_parser.react import REACT_ACT_TAG, REACT_REASONING_TAG


class MaxTokensExceededModel(FunctionModel):
    """Model that raises UnexpectedModelBehavior for max tokens exceeded."""

    def __init__(self) -> None:
        super().__init__(self._raise_max_tokens_error)

    def _raise_max_tokens_error(
        self, _messages: list[ModelMessage], _info: AgentInfo
    ) -> ModelResponse:
        """Raise UnexpectedModelBehavior with max retries message."""
        # Create a response with finish_reason="length"
        response = ModelResponse(parts=[TextPart("partial output...")], finish_reason="length")
        return response


class MaxTokensExceededWithNoTextModel(FunctionModel):
    """Model that raises UnexpectedModelBehavior for max tokens exceeded with no text output."""

    def __init__(self) -> None:
        super().__init__(self._raise_max_tokens_no_text_error)

    def _raise_max_tokens_no_text_error(
        self, _messages: list[ModelMessage], _info: AgentInfo
    ) -> ModelResponse:
        """Raise UnexpectedModelBehavior with max retries message and no text output."""
        # Create a response with finish_reason="length" but no text parts
        response = ModelResponse(parts=[], finish_reason="length")
        return response


class InvalidStringOutputModel(FunctionModel):
    """Model that returns invalid string output that can't be structured."""

    def __init__(self) -> None:
        super().__init__(self._return_invalid_string)

    def _return_invalid_string(
        self, _messages: list[ModelMessage], _info: AgentInfo
    ) -> ModelResponse:
        """Return invalid string output."""
        return ModelResponse(parts=[TextPart("not valid json at all")])


class InnerMonologueModel(FunctionModel):
    """Model that simulates inner monologue thinking method."""

    def __init__(
        self, expected_output: PlayerOutputType | str, thinking_output: str | None
    ) -> None:
        self.expected_output = expected_output
        self.thinking_output = thinking_output
        super().__init__(self._simulate_inner_monologue)

    def _simulate_inner_monologue(
        self, _messages: list[ModelMessage], _info: AgentInfo
    ) -> ModelResponse:
        """Return a response that simulates inner monologue."""
        response_parts = [
            TextPart(
                content=self.expected_output.text_part_dump()  # noqa: WPS504
                if not isinstance(self.expected_output, str)
                else self.expected_output
            )
        ]
        if self.thinking_output is not None:
            response_parts.insert(0, ThinkingPart(content=self.thinking_output))
        return ModelResponse(parts=response_parts)


class ThinkingOutLoudModel(FunctionModel):
    """Model that simulates thinking-out-loud (ReAct-style) thinking method."""

    def __init__(
        self, expected_output: PlayerOutputType | str, thinking_output: str | None
    ) -> None:
        self.expected_output = expected_output
        self.thinking_output = thinking_output
        super().__init__(self._simulate_thinking_out_loud)

    def _simulate_thinking_out_loud(
        self, _messages: list[ModelMessage], _info: AgentInfo
    ) -> ModelResponse:
        """Return a response that simulates thinking-out-loud."""
        action_as_string = (
            self.expected_output.text_part_dump()  # noqa: WPS504
            if not isinstance(self.expected_output, str)
            else self.expected_output
        )
        output_text = f"<{REACT_ACT_TAG}>{action_as_string}</{REACT_ACT_TAG}>"
        if self.thinking_output is not None:
            output_text = f"<{REACT_REASONING_TAG}>{self.thinking_output}</{REACT_REASONING_TAG}>\n{output_text}"

        return ModelResponse(parts=[TextPart(content=output_text)])
