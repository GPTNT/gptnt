from enum import Enum


class AIResponseErrorType(Enum):
    """Reasons the AI player errored."""

    # Critical errors that prevent action execution
    action_not_present = "action_not_present"
    """No action was generated or found."""
    action_parsing_failed = "action_parsing_failed"
    """Action was attempted but couldn't be parsed (malformed/wrong format)."""
    multiple_actions_present = "multiple_actions_present"
    """Multiple actions when only one was expected."""

    # Action content errors - the action was parsed but had invalid content
    invalid_som_location = "invalid_som_location"
    """Set-of-marks location is invalid (e.g., negative integer, out of range letter)."""
    out_of_bounds_coordinate = "out_of_bounds_coordinate"
    """Absolute coordinate is out of image boundary."""

    # Reasoning quality errors - non-blocking but problematic
    reasoning_absent = "reasoning_absent"
    """There is no reasoning content (missing, empty, whitespace)."""
    reasoning_split_across_blocks = "reasoning_split_across_blocks"
    """Reasoning split across multiple separate tags or locations."""
    reasoning_mixed_with_untagged_text = "reasoning_mixed_with_untagged_text"
    """Reasoning mixed with non-reasoning text outside of reasoning tags."""

    # Structural/ordering errors
    action_placed_before_reasoning = "action_placed_before_reasoning"
    """Action tag appears before reasoning is complete."""
    content_after_action_complete = "content_after_action_complete"
    """Content (text, tags, reasoning) appears after action tag is closed."""
    malformed_tag_structure = "malformed_tag_structure"
    """Tags are malformed (e.g., missing closing tag, overlapping/nested)."""

    # Infra/external errors
    max_output_tokens_exceeded = "max_output_tokens_exceeded"
    """Model exceeded max output tokens."""
    server_error = "server_error"
    """Server-side error from the AI provider."""
    guardrail_violation = "guardrail_violation"
    """Content policy or guardrail violation triggered."""

    # Fallback
    unknown = "unknown"


class InvalidResponseError(ValueError):
    """Exception raised when the AI response is invalid for some reason."""

    def __init__(
        self,
        message: str | None = None,
        *,
        response_error: list[AIResponseErrorType] | None = None,
    ) -> None:
        message = message or "The AI response is invalid."
        super().__init__(message)
        self.response_error = response_error


class ExceededMaxOutputTokensError(InvalidResponseError):
    """Exception raised when the output exceeds max output tokens."""

    def __init__(self, message: str | None = None, *, output: str | None) -> None:
        message = message or "Output exceeds maximum output token limit."
        super().__init__(message, response_error=[AIResponseErrorType.max_output_tokens_exceeded])
        self.output = output


class InvalidOutputFormatError(InvalidResponseError):
    """Exception raised when the format is invalid.

    Basically, the action doesn't create a JSON.
    """

    def __init__(
        self,
        message: str | None = None,
        *,
        output: str,
        expected_type: type | None,
        response_error: list[AIResponseErrorType] | None = None,
    ) -> None:
        message = (
            message
            or f"Output format is invalid. Output does not parse to expected type {expected_type!r}, got output: {output!r}"
        )
        super().__init__(message, response_error=response_error)
        self.output = output
        self.expected_type = expected_type


class ReasoningParsingError(InvalidOutputFormatError):
    """Exception raised when there is an error parsing reasoning."""

    def __init__(
        self, *, output: str, expected_type: type | None, response_error: list[AIResponseErrorType]
    ) -> None:
        message = f"Error parsing reasoning. Expected type {expected_type!r}, got output: {output!r}, error: {response_error!r}"
        super().__init__(message, output=output, expected_type=expected_type)
        self.output = output
        self.expected_type = expected_type
        self.response_error = response_error
