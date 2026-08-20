from typing import Any

import pytest
from pydantic_ai import Agent, ModelResponse
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel
from pytest_cases import parametrize

from gptnt.players.action_predictor import ActionPredictor
from gptnt.players.actions import DoNothingAction, SendMessageAction
from gptnt.players.conversation import Conversation
from gptnt.players.exceptions import AIResponseErrorType
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

from tests._cases.messages import image_count
from tests.players._models import (
    InvalidStringOutputModel,
    MaxTokensExceededModel,
    MaxTokensExceededWithNoTextModel,
)


def _capabilities() -> PlayerCapabilities:
    return PlayerCapabilities(
        player_name="test-player",
        player_type="ai",
        structured_output_mode="prompted",
        max_observations_per_request=16,
        interaction_location_method="coordinates",
    )


def _protocol(*, include_manual: bool = False) -> PlayerProtocol:
    return PlayerProtocol(
        role="defuser",
        communication_style="sync",
        is_playing_alone=False,
        include_manual=include_manual,
    )


def create_action_predictor(
    agent: Agent[Any, Any], capabilities: PlayerCapabilities, protocol: PlayerProtocol
) -> ActionPredictor:
    """Create an action predictor configured for one experiment."""
    conversation = Conversation.begin(
        capabilities=capabilities, protocol=protocol, legacy_manual=protocol.include_manual
    )
    predictor = ActionPredictor(agent=agent, capabilities=capabilities)
    predictor.configure_for_experiment(protocol=protocol, conversation=conversation)
    return predictor


@pytest.mark.anyio
async def test_send_request_returns_valid_output_when_model_responds_correctly() -> None:
    expected_action = SendMessageAction(message="Cut the blue wire")
    agent = Agent(TestModel(custom_output_text=expected_action.text_part_dump()), retries=0)
    predictor = create_action_predictor(
        agent=agent, capabilities=_capabilities(), protocol=_protocol()
    )

    call_result = await predictor.send_request_to_agent(message_input="Test message")

    assert call_result.ai_response_error == []
    assert call_result.output == expected_action
    assert call_result.new_messages


@pytest.mark.anyio
async def test_send_request_does_not_include_manual_in_new_messages() -> None:
    capabilities = _capabilities()
    protocol = _protocol(include_manual=True)
    expected_action = SendMessageAction(message="This is a test message")
    agent = Agent(TestModel(custom_output_text=expected_action.text_part_dump()), retries=0)
    predictor = create_action_predictor(agent=agent, capabilities=capabilities, protocol=protocol)

    manual_entry = predictor.conversation.entries[0]
    assert manual_entry.pinned
    assert image_count(manual_entry.messages) > 0

    call_result = await predictor.send_request_to_agent(message_input="Test message")

    assert image_count(call_result.new_messages) == 0
    assert image_count(predictor.conversation.render(capabilities)) > 0


@pytest.mark.anyio
@parametrize("model_class", [MaxTokensExceededModel, MaxTokensExceededWithNoTextModel])
async def test_send_request_returns_do_nothing_when_max_tokens_exceeded(
    model_class: type[Model],
) -> None:
    agent = Agent(model_class(), retries=0)
    predictor = create_action_predictor(
        agent=agent, capabilities=_capabilities(), protocol=_protocol()
    )

    call_result = await predictor.send_request_to_agent(message_input="Test message")

    assert call_result.ai_response_error == [AIResponseErrorType.max_output_tokens_exceeded]
    assert isinstance(call_result.output, DoNothingAction)
    assert call_result.raw_output is not None
    model_response = next(
        message for message in call_result.new_messages if isinstance(message, ModelResponse)
    )
    assert model_response.text is not None


@pytest.mark.anyio
async def test_send_request_returns_do_nothing_when_structuring_fails() -> None:
    agent = Agent(InvalidStringOutputModel(), retries=0)
    predictor = create_action_predictor(
        agent=agent, capabilities=_capabilities(), protocol=_protocol()
    )

    call_result = await predictor.send_request_to_agent(message_input="Test message")

    assert isinstance(call_result.output, DoNothingAction)
    assert call_result.ai_response_error == [AIResponseErrorType.action_parsing_failed]
    assert call_result.raw_output == "not valid json at all"


@pytest.mark.anyio
async def test_send_reflection_request_returns_valid_output_on_success() -> None:
    expected_message = "I need to be better."
    expected_output = SendMessageAction(message=expected_message).text_part_dump()
    agent = Agent(TestModel(custom_output_text=expected_output), retries=0)
    predictor = create_action_predictor(
        agent=agent, capabilities=_capabilities(), protocol=_protocol()
    )

    call_result = await predictor.send_reflection_request(reflection_message="What did you learn?")

    assert call_result.output == SendMessageAction(message=expected_message)
