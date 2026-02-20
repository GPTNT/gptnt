from google.genai.errors import ServerError
from pydantic_ai import (
    AgentRunError,
    ModelHTTPError,
    ModelMessage,
    ModelResponse,
    TextPart,
    ThinkingPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from gptnt.players.actions import PlayerOutputType
from gptnt.players.reasoning_parser.react import REACT_ACT_TAG, REACT_REASONING_TAG


class ContentFilteringErrorModel(FunctionModel):
    """Model that raises AgentRunError for content filtering."""

    def __init__(self) -> None:
        super().__init__(self._raise_content_filtering_error)

    def _raise_content_filtering_error(
        self, _messages: list[ModelMessage], _info: AgentInfo
    ) -> ModelResponse:
        """Raise AgentRunError with content filtering message."""
        raise AgentRunError(
            "Request was filtered due to the prompt triggering Azure OpenAI's content filtering system."
        )


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


class ExceededRequestQuotaModel(FunctionModel):
    """Model that raises ModelHTTPError for exceeded request quota."""

    def __init__(self) -> None:
        super().__init__(self._raise_request_quota_error)

    def _raise_request_quota_error(
        self, _messages: list[ModelMessage], _info: AgentInfo
    ) -> ModelResponse:
        """Raise ModelHTTPError with request quota exceeded message."""
        raise ModelHTTPError(
            status_code=429,
            model_name="gemini-3-flash-preview",
            body={
                "error": {
                    "code": 429,
                    "message": "Resource exhausted. Please try again later. Please refer to https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429 for more details.",
                    "status": "RESOURCE_EXHAUSTED",
                }
            },
        )


class GenericAgentRunErrorModel(FunctionModel):
    """Model that raises generic AgentRunError."""

    def __init__(self) -> None:
        super().__init__(self._raise_generic_error)

    def _raise_generic_error(
        self, _messages: list[ModelMessage], _info: AgentInfo
    ) -> ModelResponse:
        """Raise generic AgentRunError."""
        raise AgentRunError("Something unexpected happened")


class ServerErrorModel(FunctionModel):
    """Model that raises ServerError."""

    def __init__(self) -> None:
        super().__init__(self._raise_server_error)

    def _raise_server_error(
        self, _messages: list[ModelMessage], _info: AgentInfo
    ) -> ModelResponse:
        """Raise ServerError to simulate server-side errors."""
        raise ServerError(
            code=500, response_json={"error": {"message": "Internal server error occurred"}}
        )


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
