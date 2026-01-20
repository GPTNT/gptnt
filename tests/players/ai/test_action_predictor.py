from typing import Any

import pytest
from google.genai.errors import ServerError
from pydantic_ai import Agent, AgentRunError, ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pytest_cases import fixture, param_fixture, parametrize_with_cases

from gptnt.ktane.actions import GameActionType
from gptnt.players.actions import (
    AbsoluteCoordinate,
    AIResponseErrorType,
    DoNothingAction,
    InteractGameAction,
    PlayerOutputType,
    SendMessageAction,
    SingleAlphabetLetter,
)
from gptnt.players.ai.action_predictor import ActionPredictor
from gptnt.players.ai.message_history import MessageHistory
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

# ============================================================================
# Fixtures & Cases
# ============================================================================

interaction_location_method = param_fixture(
    "interaction_location_method", ["set-of-marks", "coordinates"]
)
structured_output_mode = param_fixture("structured_output_mode", ["prompted"])


@fixture
def capabilities(
    interaction_location_method: str, structured_output_mode: str
) -> PlayerCapabilities:
    """Fixture for PlayerCapabilities with varying interaction location methods."""
    return PlayerCapabilities(
        player_name="test_player",
        player_type="ai",
        use_structured_outputs=True,
        structured_output_mode=structured_output_mode,
        max_observation_window_length=16,
        interaction_location_method=interaction_location_method,
    )


class ProtocolCases:
    """Case class for different PlayerProtocol configurations."""

    def case_collaborative(self) -> PlayerProtocol:
        """Collaborative protocol (is_playing_alone=False, allows SendMessage)."""
        return PlayerProtocol(
            role="defuser",
            communication_style="sync",
            is_playing_alone=False,
            include_manual=True,
            receive_feedback_after_action=False,
            allow_magic_actions=False,
        )

    def case_solo(self) -> PlayerProtocol:
        """Solo protocol (is_playing_alone=True, no SendMessage)."""
        return PlayerProtocol(
            role="defuser",
            communication_style="sync",
            is_playing_alone=True,
            include_manual=True,
            receive_feedback_after_action=False,
            allow_magic_actions=False,
        )


def create_action_predictor(
    agent: Agent[Any, Any], capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> ActionPredictor:
    """Factory to create configured ActionPredictor instances."""
    message_history = MessageHistory(capabilities=capabilities, protocol=protocol)
    predictor = ActionPredictor(agent=agent, capabilities=capabilities)
    predictor.configure_for_experiment(protocol=protocol, message_history=message_history)
    return predictor


# ============================================================================
# Custom FunctionModel Implementations for Exception Testing
# ============================================================================


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


class SuccessfulOutputCases:
    """Case class for successful model outputs."""

    def case_do_nothing_action(self) -> DoNothingAction:
        """DoNothingAction output."""
        return DoNothingAction()

    def case_send_message_action(self) -> SendMessageAction:
        """SendMessageAction output."""
        return SendMessageAction(message="This is a test message")

    def case_send_message_with_special_chars(self) -> SendMessageAction:
        """SendMessageAction with special characters."""
        return SendMessageAction(message="Hello! How are you? I'm doing great.")

    def case_interact_game_set_of_marks(self) -> InteractGameAction[SingleAlphabetLetter]:
        """InteractGameAction with set-of-marks location."""
        return InteractGameAction[SingleAlphabetLetter](
            action=GameActionType.click_release, location="A"
        )

    def case_interact_game_absolute_coordinate(self) -> InteractGameAction[AbsoluteCoordinate]:
        """InteractGameAction with absolute coordinate."""
        return InteractGameAction[AbsoluteCoordinate](
            action=GameActionType.click_release, location=AbsoluteCoordinate(x=100, y=200)
        )


@pytest.mark.anyio
@parametrize_with_cases("expected_action", cases=SuccessfulOutputCases)
@parametrize_with_cases("protocol", cases=ProtocolCases)
async def test_send_request_returns_valid_output_when_model_responds_correctly(
    expected_action: PlayerOutputType, capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> None:
    """Test that send_request_to_agent returns valid output for successful responses."""

    # Check if this action type is valid for this protocol
    if isinstance(expected_action, SendMessageAction) and protocol.is_playing_alone:
        pytest.skip("SendMessage not valid when playing alone")
    if isinstance(expected_action, InteractGameAction) and protocol.role == "expert":
        pytest.skip("InteractGame not valid for expert role")

    # Check if location type matches capabilities for interact_game
    if isinstance(expected_action, InteractGameAction):
        has_coordinate_location = isinstance(expected_action.location, AbsoluteCoordinate)
        expects_coordinates = capabilities.interaction_location_method == "coordinates"
        if has_coordinate_location != expects_coordinates:
            pytest.skip(
                f"Location type mismatch: action has {'coordinate' if has_coordinate_location else 'set-of-marks'} "
                f"but capabilities expect {capabilities.interaction_location_method}"
            )

    # Create agent with TestModel and retries=0 (no output_type needed)
    agent = Agent(TestModel(custom_output_text=expected_action.text_part_dump()), retries=0)
    predictor = create_action_predictor(agent=agent, capabilities=capabilities, protocol=protocol)

    # Send request
    call_result = await predictor.send_request_to_agent(message_input="Test message")

    # Assertions
    assert call_result.ai_response_error is None
    assert call_result.output == expected_action
    assert len(call_result.new_messages) > 0


# ============================================================================
# Tests for Exception Handling
# ============================================================================


@pytest.mark.anyio
@parametrize_with_cases("protocol", cases=ProtocolCases)
async def test_send_request_handles_content_filtering_with_rephrase_request(
    capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> None:
    """Test that content filtering returns rephrase request."""
    agent = Agent(ContentFilteringErrorModel(), retries=0)
    predictor = create_action_predictor(agent=agent, capabilities=capabilities, protocol=protocol)

    # Send request
    call_result = await predictor.send_request_to_agent(message_input="Test message")

    # Assertions
    assert isinstance(call_result.output, SendMessageAction)
    assert call_result.output.message == "Can you rephrase that please?"
    assert call_result.ai_response_error == AIResponseErrorType.guardrail_violation
    assert len(call_result.new_messages) == 0  # No messages added for refusal


@pytest.mark.anyio
@parametrize_with_cases("protocol", cases=ProtocolCases)
async def test_send_request_returns_do_nothing_when_max_tokens_exceeded(
    capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> None:
    """Test that max tokens exceeded returns DoNothingAction with max_tokens_exceeded error."""
    agent = Agent(MaxTokensExceededModel(), retries=0)
    predictor = create_action_predictor(agent=agent, capabilities=capabilities, protocol=protocol)

    # Send request
    call_result = await predictor.send_request_to_agent(message_input="Test message")

    # Assertions
    assert call_result.ai_response_error == AIResponseErrorType.max_tokens_exceeded
    assert isinstance(call_result.output, DoNothingAction)
    assert call_result.raw_output != ""
    assert call_result.raw_output is not None


@pytest.mark.anyio
@parametrize_with_cases("protocol", cases=ProtocolCases)
async def test_send_request_returns_do_nothing_when_unknown_error(
    capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> None:
    """Test that unknown error returns DoNothingAction."""
    agent = Agent(GenericAgentRunErrorModel(), retries=0)
    predictor = create_action_predictor(agent=agent, capabilities=capabilities, protocol=protocol)

    # Send request
    call_result = await predictor.send_request_to_agent(message_input="Test message")

    # Assertions
    assert isinstance(call_result.output, DoNothingAction)
    assert call_result.ai_response_error == AIResponseErrorType.unknown


@pytest.mark.anyio
@parametrize_with_cases("protocol", cases=ProtocolCases)
async def test_send_request_returns_do_nothing_when_server_error(
    capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> None:
    """Test that server error returns DoNothingAction."""
    agent = Agent(ServerErrorModel(), retries=0)
    predictor = create_action_predictor(agent=agent, capabilities=capabilities, protocol=protocol)

    # Send request
    call_result = await predictor.send_request_to_agent(message_input="Test message")

    # Assertions
    assert isinstance(call_result.output, DoNothingAction)
    assert call_result.ai_response_error == AIResponseErrorType.server_error


@pytest.mark.anyio
@parametrize_with_cases("protocol", cases=ProtocolCases)
async def test_send_request_returns_do_nothing_when_structuring_fails(
    protocol: PlayerProtocol,
) -> None:
    """Test that invalid output format after structuring returns DoNothingAction."""
    # For prompted mode, we need to test when the model returns a string that can't be parsed
    # Create a modified capabilities that expects structured output but model returns bad string
    capabilities_expecting_structure = PlayerCapabilities(
        player_name="test_player",
        player_type="ai",
        use_structured_outputs=False,  # This means string output needs structuring
        structured_output_mode="prompted",
        max_observation_window_length=16,
    )

    agent = Agent(InvalidStringOutputModel(), retries=0)
    predictor = create_action_predictor(
        agent=agent, capabilities=capabilities_expecting_structure, protocol=protocol
    )

    # Send request
    call_result = await predictor.send_request_to_agent(message_input="Test message")

    # Assertions
    assert isinstance(call_result.output, DoNothingAction)
    assert call_result.ai_response_error == AIResponseErrorType.invalid_format
    assert call_result.raw_output == "not valid json at all"
