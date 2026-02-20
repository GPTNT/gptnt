from typing import Any

import pytest
from pydantic_ai import Agent, BinaryContent, UserPromptPart
from pydantic_ai.models.test import TestModel
from pytest_cases import parametrize_with_cases

from gptnt.players.actions import (
    DoNothingAction,
    InteractGameAction,
    PlayerOutputType,
    SendMessageAction,
)
from gptnt.players.ai.action_predictor import ActionPredictor
from gptnt.players.ai.messages.message_history import MessageHistory
from gptnt.players.exceptions import AIResponseErrorType
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

from tests._cases.capabilities import CapabilitiesCases
from tests._cases.outputs import PredictedActionCases, ReflectionOutputCases
from tests._cases.protocol import ProtocolCases
from tests.players._models import (
    ContentFilteringErrorModel,
    ExceededRequestQuotaModel,
    GenericAgentRunErrorModel,
    InvalidStringOutputModel,
    MaxTokensExceededModel,
    ServerErrorModel,
)


def create_action_predictor(
    agent: Agent[Any, Any], capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> ActionPredictor:
    """Factory to create configured ActionPredictor instances."""
    message_history = MessageHistory(capabilities=capabilities, protocol=protocol)
    predictor = ActionPredictor(agent=agent, capabilities=capabilities)
    predictor.configure_for_experiment(protocol=protocol, message_history=message_history)
    return predictor


@parametrize_with_cases("action", cases=PredictedActionCases)
def test_actions_are_parsed_correctly_from_json(action: PlayerOutputType) -> None:
    """Test that the actions are parsed correctly.

    This is a regression test to ensure that the actions are parsed correctly.
    """
    action_as_json = action.model_dump(mode="json", exclude_none=True, exclude_defaults=True)

    # Note: actions can be validated by their name or the value, so we check that too
    if isinstance(action, InteractGameAction):
        action_as_json["action"] = action.action.name

    test_model = Agent(TestModel(custom_output_args=action_as_json), output_type=action.__class__)
    output = test_model.run_sync("message")

    assert output.output == action


@pytest.mark.anyio
@parametrize_with_cases("expected_action", cases=PredictedActionCases)
@parametrize_with_cases("protocol", cases=ProtocolCases)
async def test_send_request_returns_valid_output_when_model_responds_correctly(
    expected_action: PlayerOutputType, capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> None:
    """Test that send_request_to_agent returns valid output for successful responses."""
    CapabilitiesCases.check_expected_output_with_capabilities(
        expected_output=expected_action, capabilities=capabilities
    )
    ProtocolCases.check_expected_output_with_protocol(
        expected_output=expected_action, protocol=protocol
    )

    # Create agent with TestModel and retries=0 (no output_type needed)
    agent = Agent(TestModel(custom_output_text=expected_action.text_part_dump()), retries=0)
    predictor = create_action_predictor(agent=agent, capabilities=capabilities, protocol=protocol)

    # Send request
    call_result = await predictor.send_request_to_agent(message_input="Test message")

    # Assertions
    assert len(call_result.ai_response_error) == 0
    assert call_result.output == expected_action
    assert len(call_result.new_messages) > 0


@pytest.mark.anyio
@parametrize_with_cases("protocol", cases=ProtocolCases)
async def test_send_request_does_not_include_manual_in_new_messages(
    capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> None:
    """Test that manual is not included in new_messages after send_request_to_agent."""
    if not protocol.include_manual:
        pytest.skip("Protocol does not include manual, skipping test.")

    # Create agent with TestModel that returns a SendMessageAction
    expected_action = SendMessageAction(message="This is a test message")
    agent = Agent(TestModel(custom_output_text=expected_action.text_part_dump()), retries=0)
    predictor = create_action_predictor(agent=agent, capabilities=capabilities, protocol=protocol)

    # Send request
    call_result = await predictor.send_request_to_agent(message_input="Test message")

    # We iterate through any modelrequests and make sure there's no binary content. this is fine
    # because we are not sending any observations in the above request.
    for message in call_result.new_messages:
        for part in message.parts:
            if isinstance(part, UserPromptPart) and not isinstance(part.content, str):
                assert all(not isinstance(content, BinaryContent) for content in part.content)

    # Make sure the manual is in the history though
    assert predictor.message_history.messages_per_run[0].contains_manual


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
    assert call_result.ai_response_error == [AIResponseErrorType.guardrail_violation]
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
    assert call_result.ai_response_error == [AIResponseErrorType.max_output_tokens_exceeded]
    assert isinstance(call_result.output, DoNothingAction)
    assert call_result.raw_output != ""
    assert call_result.raw_output is not None


@pytest.mark.anyio
@parametrize_with_cases("protocol", cases=ProtocolCases)
@pytest.mark.skip(reason="This is running incredibly slow? Needs investigation.")
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
    assert call_result.ai_response_error == [AIResponseErrorType.unknown]


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
    assert call_result.ai_response_error == [AIResponseErrorType.server_error]


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
        structured_output_mode="prompted",
        max_observations_per_request=16,
    )

    agent = Agent(InvalidStringOutputModel(), retries=0)
    predictor = create_action_predictor(
        agent=agent, capabilities=capabilities_expecting_structure, protocol=protocol
    )

    # Send request
    call_result = await predictor.send_request_to_agent(message_input="Test message")

    # Assertions
    assert isinstance(call_result.output, DoNothingAction)
    assert call_result.ai_response_error == [AIResponseErrorType.unknown]
    assert call_result.raw_output == "not valid json at all"


@pytest.mark.anyio
@parametrize_with_cases("protocol", cases=ProtocolCases)
async def test_send_request_return_do_nothing_when_request_quota_error(
    capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> None:
    """Test that request quota errors are raised and categorized correctly."""
    agent = Agent(ExceededRequestQuotaModel(), retries=0)
    predictor = create_action_predictor(agent=agent, capabilities=capabilities, protocol=protocol)

    # Send request and expect it to return DoNothingAction due to request quota error
    call_result = await predictor.send_request_to_agent(message_input="Test message")

    # Assertions
    assert isinstance(call_result.output, DoNothingAction)
    assert call_result.ai_response_error == [AIResponseErrorType.server_error]


# ============================================================================
# Tests for send_reflection_request
# ============================================================================


@pytest.mark.anyio
@parametrize_with_cases("expected_output", cases=ReflectionOutputCases)
@parametrize_with_cases("protocol", cases=ProtocolCases)
async def test_send_reflection_request_returns_valid_output_on_success(
    expected_output: str, capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> None:
    """Test that send_reflection_request returns valid SendMessageAction on success."""
    agent = Agent(TestModel(custom_output_text=expected_output), retries=0)
    predictor = create_action_predictor(agent=agent, capabilities=capabilities, protocol=protocol)

    # Send reflection request
    call_result = await predictor.send_reflection_request(reflection_message="What did you learn?")

    # Assertions
    assert isinstance(call_result.output, SendMessageAction)
    assert call_result.output.message == ReflectionOutputCases.message
    # assert len(call_result.new_messages) > 0


@pytest.mark.anyio
@parametrize_with_cases("protocol", cases=ProtocolCases)
async def test_send_reflection_request_handles_agent_run_error_gracefully(
    capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> None:
    """Test that AgentRunError during reflection returns default '<error>' message."""
    agent = Agent(GenericAgentRunErrorModel(), retries=0)
    predictor = create_action_predictor(agent=agent, capabilities=capabilities, protocol=protocol)

    # Send reflection request
    call_result = await predictor.send_reflection_request(reflection_message="What did you learn?")

    # Assertions
    assert isinstance(call_result.output, SendMessageAction)
    assert call_result.output.message == "<error>"
    assert call_result.ai_response_error == [AIResponseErrorType.unknown]
    assert call_result.usage is not None  # Should have empty usage
    # Should still have messages (the error message added)
    # assert len(call_result.new_messages) > 0
