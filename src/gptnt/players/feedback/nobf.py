from dataclasses import dataclass

from gptnt.players.actions import AgentCallResult, AIResponseErrorType, PlayerOutputType
from gptnt.services.events.player import PlayerMessage


@dataclass(kw_only=True)
class NaughtyOutputBehaviourFeedbackGenerator:
    """Generate feedback based on naughty output behaviour."""

    def __post_init__(self) -> None:
        """Setup the feedback handlers."""
        # We don't handle the guardrail violations here, as those are an edge case of the AI response error (as triggered by the user).
        self.handlers = {  # pyright: ignore[reportUninitializedInstanceVariable]
            AIResponseErrorType.invalid_som_location: self.handle_invalid_som_location_error,
            AIResponseErrorType.out_of_bounds_coordinate: self.handle_out_of_bounds_coordinate_error,
            AIResponseErrorType.server_error: self.handle_server_error,
            AIResponseErrorType.invalid_format: self.handle_invalid_format,
            AIResponseErrorType.max_tokens_exceeded: self.handle_max_tokens_exceeded,
            AIResponseErrorType.unknown: self.handle_unknown_error,
        }

    def generate(
        self, *, agent_call_result: AgentCallResult[PlayerOutputType]
    ) -> PlayerMessage[str] | None:
        """Generate feedback based on the agent call result."""
        error = agent_call_result.ai_response_error
        if error:
            error_handler = self.handlers.get(error)  # noqa: WPS110

            if error_handler:
                feedback_message = error_handler()

                return self.wrap_feedback_message(feedback_message)

        return None

    def handle_invalid_som_location_error(self) -> str:
        """Handle invalid SOM location feedback."""
        return "The action you generated contained an invalid location marker, causing you to skip your previous turn. Double check the location marker in your action and ensure it corresponds to a valid location in the frame and try again."

    def handle_out_of_bounds_coordinate_error(self) -> str:
        """Handle out of bounds coordinate feedback."""
        return "The action you generated contained an out-of-bounds coordinate, causing you to skip your previous turn. Double check all coordinates you use in your actions and ensure they are within the valid range."

    def handle_server_error(self) -> str:
        """Handle server error feedback."""
        return "There was a server error while you were generating your response, causing you to skip your previous turn."

    def handle_invalid_format(self) -> str:
        """Handle invalid format feedback."""
        return "The response you generated was in an invalid format, causing you to skip your previous turn. Double check the format of your responses and ensure it is a valid JSON as described in the instructions."

    def handle_max_tokens_exceeded(self) -> str:
        """Handle max tokens exceeded feedback."""
        return "It seems like your thoughts or message were too verbose and you exhausted your word limit, causing you to skip your previous turn. You must use fewer words and be more concise in your thoughts."

    def handle_unknown_error(self) -> str:
        """Handle unknown error feedback."""
        return "An unknown error occurred while processing your output, causing you to skip your previous turn."

    def wrap_feedback_message(self, feedback_message: str) -> PlayerMessage[str]:
        """Wrap the feedback message in exec-feedback tags."""
        return PlayerMessage(
            message=f"<execution-feedback>{feedback_message}</execution-feedback>"
        )
