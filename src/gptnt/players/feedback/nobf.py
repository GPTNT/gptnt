from collections.abc import Callable
from dataclasses import dataclass, field

from gptnt.players.actions import PlayerOutputType
from gptnt.players.exceptions import AIResponseErrorType
from gptnt.players.result import AgentCallResult


@dataclass(kw_only=True)
class NaughtyOutputBehaviourFeedbackGenerator:
    """Generate feedback based on naughty output behaviour."""

    feedback_xml_tag: str = "execution-feedback"

    _handlers: dict[AIResponseErrorType, Callable[[], str]] = field(init=False)

    def __post_init__(self) -> None:
        """Setup the feedback handlers."""
        # We don't handle the guardrail violations here, as those are an edge case of the AI response error (as triggered by the user).
        self._handlers = {
            # Critical errors that prevent action execution
            AIResponseErrorType.action_not_present: self._handle_action_not_present,
            AIResponseErrorType.action_parsing_failed: self._handle_invalid_format,
            AIResponseErrorType.multiple_actions_present: self._handle_multiple_actions_present,
            # Action content errors - the action was parsed but had invalid content
            AIResponseErrorType.invalid_som_location: self._handle_invalid_som_location_error,
            AIResponseErrorType.out_of_bounds_coordinate: self._handle_out_of_bounds_coordinate_error,
            # Reasoning quality errors - non-blocking but problematic
            AIResponseErrorType.reasoning_absent: self._handle_reasoning_absent,
            AIResponseErrorType.reasoning_split_across_blocks: self._handle_reasoning_split_across_blocks,
            AIResponseErrorType.reasoning_mixed_with_untagged_text: self._handle_reasoning_mixed_with_untagged_text,
            # Structural/ordering errors
            AIResponseErrorType.action_placed_before_reasoning: self._handle_action_placed_before_reasoning,
            AIResponseErrorType.content_after_action_complete: self._handle_content_after_action_complete,
            AIResponseErrorType.malformed_tag_structure: self._handle_malformed_tag_structure,
            # Infra/external errors (note: guardrail violations are not handled here)
            AIResponseErrorType.max_output_tokens_exceeded: self._handle_max_tokens_exceeded,
            AIResponseErrorType.server_error: self._handle_server_error,
            # Fallback
            AIResponseErrorType.unknown: self._handle_unknown_error,
        }

    def generate(self, *, agent_call_result: AgentCallResult[PlayerOutputType]) -> str | None:
        """Generate feedback based on the agent call result."""
        if not agent_call_result.ai_response_error:
            return None

        all_feedback = []

        for error in agent_call_result.ai_response_error:
            if error_handler := self._handlers.get(error):
                feedback_message = error_handler()
                all_feedback.append(feedback_message)

        combined_feedback = " ".join(all_feedback).strip()
        if not combined_feedback:
            return None
        return self._wrap_feedback_message(combined_feedback)

    # Critical errors that prevent action execution

    def _handle_action_not_present(self) -> str:
        return "The response you generated in your previous turn contained no action, causing you to skip your previous turn. Make sure to include an action in your response."

    def _handle_invalid_format(self) -> str:
        return "The response you generated in your previous turn was in an invalid format, causing you to skip your previous turn. Double check the format of your responses and ensure it is a valid JSON as described in the instructions."

    def _handle_multiple_actions_present(self) -> str:
        return "The response you generated in your previous turn contained multiple actions when only one was expected. Only the first action you generated was executed and the other actions you generated were lost. Make sure to include only one action in your response."

    # Action content errors - the action was parsed but had invalid content

    def _handle_invalid_som_location_error(self) -> str:
        return "The action you generated contained an invalid location marker, causing you to skip your previous turn. Double check the location marker in your action and ensure it corresponds to a valid location in the frame and try again."

    def _handle_out_of_bounds_coordinate_error(self) -> str:
        return "The action you generated contained an out-of-bounds coordinate, causing you to skip your previous turn. Double check all coordinates you use in your actions and ensure they are within the valid range."

    # Reasoning quality errors - non-blocking but problematic

    def _handle_reasoning_absent(self) -> str:
        return "The response you generated in your previous turn did not include any thoughts, but this is important for your decision making. Ensure to reason before responding in future."

    def _handle_reasoning_split_across_blocks(self) -> str:
        return "The reasoning you generated in your previous turn was split across multiple separate tags or locations, which is not the expected format. Ensure you keep your reasoning in a single, coherent block in future responses."

    def _handle_reasoning_mixed_with_untagged_text(self) -> str:
        return "The reasoning you generated in your previous turn was mixed with non-reasoning text outside of reasoning tags, which is not the expected format. Ensure you keep your reasoning separate from other text in future responses."

    # Structural/ordering errors

    def _handle_action_placed_before_reasoning(self) -> str:
        return "In your previous turn, you generated an action before your reasoning was complete, which means you may not have thought your action through completely. Ensure you wrap up your thought process before deciding on an action in future responses."

    def _handle_content_after_action_complete(self) -> str:
        return "In your previous turn, you continued to generate content (text, tags, reasoning) after providing your action, which is not the expected format. Ensure you avoid adding any content after you have generated an action in future responses."

    def _handle_malformed_tag_structure(self) -> str:  # TBC
        return "The tags in your previous response were malformed (e.g., missing closing tag, overlapping/nested tags), which can lead to parsing issues. Ensure you use proper tag structures in future responses."

    # Infra/external errors (note: guardrail violations are not handled here)

    def _handle_max_tokens_exceeded(self) -> str:
        return "It seems like your thoughts or message were too verbose and you exhausted your word limit, causing you to skip your previous turn. You must use fewer words and be more concise in your thoughts in future."

    def _handle_server_error(self) -> str:
        return "There was a server error while you were generating your response, causing you to skip your previous turn."

    # Fallback

    def _handle_unknown_error(self) -> str:
        return "An unknown error occurred while processing your output, causing you to skip your previous turn."

    # Utility Methods

    def _wrap_feedback_message(self, feedback_message: str) -> str:
        """Wrap the feedback message in exec-feedback tags."""
        return f"<{self.feedback_xml_tag}>{feedback_message}</{self.feedback_xml_tag}>"
