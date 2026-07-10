import datetime
from dataclasses import replace
from itertools import accumulate

import pytest
from pydantic_ai import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RequestUsage,
    RunUsage,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.usage import UsageLimits
from pytest_cases import fixture, parametrize_with_cases

from gptnt.players.actions import SendMessageAction
from gptnt.players.history.message_history import MessageHistory
from gptnt.players.history.message_transformer import (
    coerce_tool_output_into_native_output,
    ensure_messages_have_valid_final_response,
    remove_binary_content_from_model_request,
)
from gptnt.players.history.single_run import SingleRun
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

from tests._cases.messages import TEST_TOKENS_PER_IMAGE, ModelMessageCases
from tests._cases.protocol import ProtocolCases

# ============================================================================
# Fixtures & Factories
# ============================================================================


@fixture
def model_request(mock_image_bytes: bytes, num_observations: int) -> ModelRequest:
    """A model request.

    Observations always come after the text.
    """
    observations = [
        BinaryContent(data=mock_image_bytes, media_type="image/png")
    ] * num_observations
    return ModelRequest(
        parts=[
            UserPromptPart(
                content=["What should I do next?", *observations],
                timestamp=datetime.datetime(2025, 1, 1, 12, 0, 0, tzinfo=datetime.UTC),
            )
        ],
        run_id="test-run-001",
    )


input_text_tokens = 20


@fixture
def simple_text_response(num_observations: int, tokens_per_image: int) -> ModelResponse:
    """A simple text model response."""
    return ModelResponse(
        parts=[
            TextPart(
                content=SendMessageAction(
                    message="You should press the red button."
                ).text_part_dump()
            )
        ],
        usage=RequestUsage(
            input_tokens=input_text_tokens + (num_observations * tokens_per_image),
            output_tokens=50,
        ),
        model_name="test_model",
        timestamp=datetime.datetime(2025, 1, 1, 12, 0, 1, tzinfo=datetime.UTC),
        provider_name="test_provider",
        finish_reason="stop",
        run_id="test-run-001",
    )


@fixture
def tool_call_response(num_observations: int, tokens_per_image: int) -> ModelResponse:
    """A model response with a tool call."""
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool_name="final_result_interact",
                args='{"action":"click","coordinates":{"x":100,"y":200}}',
                tool_call_id="call_123",
            )
        ],
        usage=RequestUsage(
            input_tokens=100 + num_observations * tokens_per_image, output_tokens=30
        ),
        model_name="test_model",
        timestamp=datetime.datetime(2025, 1, 1, 12, 0, 1, tzinfo=datetime.UTC),
        provider_name="test_provider",
        finish_reason="tool_call",
        run_id="test-run-001",
    )


@fixture
def tool_call_response_sequence(tool_call_response: ModelResponse) -> list[ModelMessage]:
    return [
        tool_call_response,
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="final_result_interact",
                    content="Final result processed.",
                    tool_call_id="call_JDbp0oRA7ZgojQoYY121Qw1F",
                    timestamp=datetime.datetime(
                        2025, 12, 4, 19, 34, 16, 407597, tzinfo=datetime.UTC
                    ),
                )
            ],
            run_id="3646f60f-ae3c-43cb-82a0-b87025f4c41b",
        ),
    ]


@fixture
def capabilities(preserve_last_frame_for_n_turns: int) -> PlayerCapabilities:
    """PlayerCapabilities."""
    return PlayerCapabilities(
        player_name="test-player",
        player_type="ai",
        structured_output_mode="prompted",
        interaction_location_method="coordinates",
        preserve_last_frame_for_n_turns=preserve_last_frame_for_n_turns,
        tokens_per_image=TEST_TOKENS_PER_IMAGE,
        usage_limits=UsageLimits(),
    )


class TestMessageHistoryBasics:
    """Test basic MessageHistory operations."""

    @parametrize_with_cases("protocol", cases=ProtocolCases)
    def test_initialization(
        self, capabilities: PlayerCapabilities, protocol: PlayerProtocol
    ) -> None:
        """Test MessageHistory initialization."""
        history = MessageHistory(
            capabilities=capabilities, protocol=protocol, force_convert_tool_output_to_native=False
        )

        # if the protocol has the manual, then we expect it to be in the history on init
        if protocol.include_manual:
            assert not history.is_empty
            assert len(history) == 1
            assert bool(history)
            assert len(history.to_history()) == 1
        else:
            assert history.is_empty
            assert len(history) == 0
            assert not history
            assert history.num_times_truncated == 0
            assert len(history.to_history()) == 0

    @parametrize_with_cases("protocol", cases=ProtocolCases)
    @parametrize_with_cases("messages", cases=ModelMessageCases)
    def test_update_adds_messages(
        self,
        capabilities: PlayerCapabilities,
        protocol: PlayerProtocol,
        messages: list[ModelMessage],
    ) -> None:
        """Test that update() adds messages correctly."""
        history = MessageHistory(
            capabilities=capabilities, protocol=protocol, force_convert_tool_output_to_native=False
        )

        usage = RunUsage(
            requests=1, input_tokens=history.usage.total_tokens + 200, output_tokens=50
        )
        history.update(new_messages=messages, usage=usage)

        assert not history.is_empty
        assert bool(history)
        assert history.usage == usage

        assert len(history) == 2 if protocol.include_manual else len(history) == 1
        assert (
            len(history.to_history()) == len(messages) + 1
            if protocol.include_manual
            else len(history.to_history()) == len(messages)
        )

    @parametrize_with_cases("protocol", cases=ProtocolCases)
    @parametrize_with_cases("messages", cases=ModelMessageCases)
    def test_multiple_updates(
        self,
        capabilities: PlayerCapabilities,
        protocol: PlayerProtocol,
        messages: list[ModelMessage],
    ) -> None:
        """Test multiple updates to message history."""
        history = MessageHistory(
            capabilities=capabilities, protocol=protocol, force_convert_tool_output_to_native=False
        )

        usage = RunUsage(
            requests=1, input_tokens=history.usage.total_tokens + 200, output_tokens=50
        )
        history.update(new_messages=messages, usage=usage)
        history.update(
            new_messages=messages,
            usage=RunUsage(input_tokens=history.usage.total_tokens + 200, output_tokens=50),
        )

        expected_num_runs = 3 if protocol.include_manual else 2
        expected_num_messages = (
            2 * len(messages) + 1 if protocol.include_manual else 2 * len(messages)
        )

        assert len(history) == expected_num_runs
        assert len(history.to_history()) == expected_num_messages

    @parametrize_with_cases("protocol", cases=ProtocolCases)
    @parametrize_with_cases("messages", cases=ModelMessageCases)
    def test_single_run_tracks_metadata(
        self,
        capabilities: PlayerCapabilities,
        protocol: PlayerProtocol,
        messages: list[ModelMessage],
    ) -> None:
        """Test that SingleRun tracks metadata correctly."""
        history = MessageHistory(
            capabilities=capabilities, protocol=protocol, force_convert_tool_output_to_native=False
        )

        usage = RunUsage(
            requests=1, input_tokens=history.usage.total_tokens + 200, output_tokens=50
        )
        history.update(new_messages=messages, usage=usage)

        expected_num_runs = 2 if protocol.include_manual else 1
        expected_run_idx = 1 if protocol.include_manual else 0

        assert len(history.messages_per_run) == expected_num_runs
        run = history.messages_per_run[-1]
        assert isinstance(run, SingleRun)
        assert run.idx == expected_run_idx

        # First message with protocol.include_manual=True should have contains_manual=True
        assert history.messages_per_run[0].contains_manual == protocol.include_manual


class TestToolOutputCoercion:
    """Test coerce_tool_output_into_native_output functionality."""

    def test_coerce_tool_call_to_text(self, tool_call_response: ModelResponse) -> None:
        """Test that tool calls are converted to text format."""
        result = coerce_tool_output_into_native_output([tool_call_response])

        assert len(result) == 1
        response = result[0]
        assert isinstance(response, ModelResponse)
        assert len(response.parts) == 1
        part = response.parts[0]
        assert isinstance(part, TextPart)
        assert "interact" in part.content
        assert "result" in part.content

    def test_preserves_text_parts(self, simple_text_response: ModelResponse) -> None:
        """Test that regular text parts are preserved."""
        result = coerce_tool_output_into_native_output([simple_text_response])

        assert len(result) == 1
        assert result[0] == simple_text_response

    @parametrize_with_cases("messages", cases=ModelMessageCases, glob="*tool_call*")
    def test_coerce_multi_turn_tool_call_sequence(self, messages: list[ModelMessage]) -> None:
        """Test coercion of a sequence of messages with tool calls."""
        result = coerce_tool_output_into_native_output(messages)

        # Make sure we don't lose any responses, like we need to verify the tool call requests are
        # gone but the responses are still there just with the tool call parts converted to text
        # parts
        num_requests_with_tool_return_parts = [
            1
            for message in messages
            if isinstance(message, ModelRequest)
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        ]
        assert len(result) == len(messages) - sum(num_requests_with_tool_return_parts)

        for message in result:
            if isinstance(message, ModelRequest):
                for part in message.parts:
                    assert not isinstance(part, ToolReturnPart)
            if isinstance(message, ModelResponse):
                for part in message.parts:
                    assert not isinstance(part, ToolCallPart)


class TestEnsureValidFinalResponse:
    """Test ensure_messages_have_valid_final_response functionality."""

    def test_empty_messages(self) -> None:
        """Test handling of empty message list."""
        result = ensure_messages_have_valid_final_response([])
        assert len(result) == 0

    def test_adds_response_if_missing(self, model_request: ModelRequest) -> None:
        """Test that a response is added if none exists."""
        messages = [model_request]

        result = ensure_messages_have_valid_final_response(messages)

        assert len(result) == 2
        assert isinstance(result[1], ModelResponse)
        assert len(result[1].parts) == 1
        assert isinstance(result[1].parts[0], TextPart)
        assert result[1].parts[0].content == ""

    def test_preserves_existing_response(
        self, model_request: ModelRequest, simple_text_response: ModelResponse
    ) -> None:
        """Test that existing responses are preserved."""
        messages = [model_request, simple_text_response]

        result = ensure_messages_have_valid_final_response(messages)

        assert len(result) == 2
        assert result == messages


class TestObservationRemoval:
    """Test observation removal from messages."""

    def test_remove_binary_content_basic(
        self, model_request: ModelRequest, num_observations: int
    ) -> None:
        """Test basic binary content removal."""
        if num_observations == 0:
            pytest.skip("Pointless test when no observations")

        num_removed, clean_message = remove_binary_content_from_model_request(
            model_request, keep_last_observation=False
        )

        assert num_removed == num_observations
        assert isinstance(clean_message, ModelRequest)
        part = clean_message.parts[0]
        assert isinstance(part, UserPromptPart)
        assert isinstance(part.content, list)
        # Should only have text, no BinaryContent
        assert all(not isinstance(item, BinaryContent) for item in part.content)

    def test_keep_last_observation(
        self, model_request: ModelRequest, num_observations: int
    ) -> None:
        """Test keeping the last observation."""
        if num_observations == 0:
            pytest.skip("Pointless test when no observations")

        num_removed, clean_message = remove_binary_content_from_model_request(
            model_request, keep_last_observation=True
        )

        assert num_removed == (num_observations - 1)
        assert isinstance(clean_message, ModelRequest)
        part = clean_message.parts[0]
        assert isinstance(part, UserPromptPart)
        assert isinstance(part.content, list)
        # Should have exactly ONE BinaryContent item (the last observation)
        binary_items = [item for item in part.content if isinstance(item, BinaryContent)]
        assert len(binary_items) == 1, (
            f"Expected exactly 1 observation, but found {len(binary_items)}"
        )

    @parametrize_with_cases("protocol", cases=ProtocolCases, glob="*defuser*")
    def test_defuser_removes_observations_on_update(
        self,
        capabilities: PlayerCapabilities,
        protocol: PlayerProtocol,
        model_request: ModelRequest,
        simple_text_response: ModelResponse,
        preserve_last_frame_for_n_turns: int,
        num_observations: int,
    ) -> None:
        """Test that defuser role removes observations.

        We are not checking the manual here because include_manual=False in this test.
        """
        if num_observations == 0:
            pytest.skip("Pointless test when no observations")

        history = MessageHistory(capabilities=capabilities, protocol=protocol)

        history.update(
            new_messages=[model_request, simple_text_response],
            usage=RunUsage(
                requests=1,
                input_tokens=history.usage.total_tokens + simple_text_response.usage.input_tokens,
                output_tokens=simple_text_response.usage.output_tokens,
            ),
        )

        messages = history.to_history()
        request = messages[1] if protocol.include_manual else messages[0]
        assert isinstance(request, ModelRequest)
        part = request.parts[0]
        assert isinstance(part, UserPromptPart)
        assert isinstance(part.content, list)

        binary_items = [item for item in part.content if isinstance(item, BinaryContent)]

        # If preserve_last_frame_for_n_turns=0, no observations should be kept otherwise one should
        # be kept.
        if preserve_last_frame_for_n_turns == 0:
            assert len(binary_items) == 0, (
                f"Expected 0 images (observations removed), got {len(binary_items)}"
            )
        if preserve_last_frame_for_n_turns > 0:
            assert len(binary_items) == 1, (
                f"Expected 1 image (last observation kept), got {len(binary_items)}"
            )

        # All text should still be present (text is not removed, only binary content)
        text_items = [item for item in part.content if isinstance(item, str)]
        assert len(text_items) == 1, f"Expected 1 text item, got {len(text_items)}"

        # To compare the token counts, we need to account for any manual tokens
        manual_tokens = 0
        if protocol.include_manual:
            manual_tokens = (
                history.messages_per_run[0].input_tokens
                + history.messages_per_run[0].output_tokens
            )
        num_obs_removed = num_observations - len(binary_items)
        assert (
            history.usage.input_tokens - manual_tokens
            == simple_text_response.usage.input_tokens
            - (num_obs_removed * history.token_accountant.tokens_per_image)
        )


class TestObservationWindow:
    """Test observation window management."""

    @parametrize_with_cases("protocol", cases=ProtocolCases, glob="*defuser*")
    def test_removes_old_observations_outside_window(
        self,
        capabilities: PlayerCapabilities,
        protocol: PlayerProtocol,
        model_request: ModelRequest,
        simple_text_response: ModelResponse,
        preserve_last_frame_for_n_turns: int,
        num_observations: int,
    ) -> None:
        """Test that observations outside the window are removed."""
        if preserve_last_frame_for_n_turns != 1:
            pytest.skip("This test only applies to window size of 1")
        if num_observations == 0:
            pytest.skip("Pointless test when no observations")

        history = MessageHistory(capabilities=capabilities, protocol=protocol)

        # Add first turn with observation
        history.update(
            new_messages=[model_request, simple_text_response],
            usage=RunUsage(
                requests=1,
                input_tokens=history.usage.total_tokens + simple_text_response.usage.input_tokens,
                output_tokens=simple_text_response.usage.output_tokens,
            ),
        )
        # Add second turn with observation
        history.update(
            new_messages=[model_request, simple_text_response],
            usage=RunUsage(
                requests=1,
                input_tokens=history.usage.total_tokens + simple_text_response.usage.input_tokens,
                output_tokens=simple_text_response.usage.output_tokens,
            ),
        )

        # Now call the method to remove old observations
        history.remove_observations_from_previous_messages()

        first_run_index = 1 if protocol.include_manual else 0
        # if we have the manual, it should have obs in it
        if protocol.include_manual:
            first_run = history.messages_per_run[0]
            assert first_run.contains_binary_content
            assert first_run.contains_manual

        # First turn should have no observations (outside window)
        first_run = history.messages_per_run[first_run_index]
        first_request = history.messages_per_run[first_run_index].messages[0]
        assert isinstance(first_request, ModelRequest)
        part = first_request.parts[0]
        assert isinstance(part, UserPromptPart)
        assert isinstance(part.content, list)
        binary_items = [item for item in part.content if isinstance(item, BinaryContent)]
        assert len(binary_items) == 0, (
            f"Expected 0 observations in first turn, got {len(binary_items)}"
        )
        assert first_run.input_tokens == simple_text_response.usage.input_tokens - (
            num_observations * history.token_accountant.tokens_per_image
        )

        # Second turn (last) should still have exactly 1 observation (within window)
        second_run = history.messages_per_run[first_run_index + 1]
        second_request = history.messages_per_run[first_run_index + 1].messages[0]
        assert isinstance(second_request, ModelRequest)
        part = second_request.parts[0]
        assert isinstance(part, UserPromptPart)
        assert isinstance(part.content, list)
        binary_items = [item for item in part.content if isinstance(item, BinaryContent)]
        assert len(binary_items) == 1, (
            f"Expected 1 observation in second turn, got {len(binary_items)}"
        )
        assert second_run.input_tokens == simple_text_response.usage.input_tokens - (
            (num_observations - 1) * history.token_accountant.tokens_per_image
        )

    @parametrize_with_cases("protocol", cases=ProtocolCases, glob="*defuser*")
    def test_window_of_n_keeps_last_n_observations(
        self,
        capabilities: PlayerCapabilities,
        protocol: PlayerProtocol,
        model_request: ModelRequest,
        simple_text_response: ModelResponse,
        preserve_last_frame_for_n_turns: int,
        num_observations: int,
    ) -> None:
        """Test that window of n keeps last n turns with observations."""
        history = MessageHistory(capabilities=capabilities, protocol=protocol)

        # Add turns
        for _ in range(3 + preserve_last_frame_for_n_turns):
            usage = RunUsage(
                requests=1,
                input_tokens=history.usage.total_tokens + simple_text_response.usage.input_tokens,
                output_tokens=simple_text_response.usage.output_tokens,
            )
            history.update(new_messages=[model_request, simple_text_response], usage=usage)

        history.remove_observations_from_previous_messages()

        # if we have the manual, it should have obs in it
        if protocol.include_manual:
            first_run = history.messages_per_run[0]
            assert first_run.contains_binary_content
            assert first_run.contains_manual

        for run in history.messages_per_run:
            if run.idx == 0 and protocol.include_manual:
                # Skip manual run
                continue

            is_within_window = (
                len(history.messages_per_run) - run.idx <= preserve_last_frame_for_n_turns
            )
            request = run.messages[0]
            assert isinstance(request, ModelRequest)
            part = request.parts[0]
            assert isinstance(part, UserPromptPart)
            assert isinstance(part.content, list)
            binary_items = [item for item in part.content if isinstance(item, BinaryContent)]
            expected_obs = 1 if is_within_window and num_observations > 0 else 0
            assert len(binary_items) == expected_obs, (
                f"Expected {expected_obs} observations in turn {run.idx}, got {len(binary_items)}"
            )
            expected_input_tokens = simple_text_response.usage.input_tokens - (
                (num_observations - expected_obs) * history.token_accountant.tokens_per_image
            )
            assert run.input_tokens == expected_input_tokens

    @parametrize_with_cases("protocol", cases=ProtocolCases, glob="*defuser*")
    def test_incremental_window_updates_on_each_turn(
        self,
        capabilities: PlayerCapabilities,
        protocol: PlayerProtocol,
        model_request: ModelRequest,
        simple_text_response: ModelResponse,
        preserve_last_frame_for_n_turns: int,
        num_observations: int,
    ) -> None:
        """Test that window correctly updates as each turn is added."""
        history = MessageHistory(capabilities=capabilities, protocol=protocol)

        for _turn_idx in range(5):
            usage = RunUsage(
                requests=1,
                input_tokens=history.usage.total_tokens + simple_text_response.usage.input_tokens,
                output_tokens=simple_text_response.usage.output_tokens,
            )
            history.update(new_messages=[model_request, simple_text_response], usage=usage)
            history.remove_observations_from_previous_messages()

            for run in history.messages_per_run:
                # if we have the manual, it should have obs in it and thats it
                if run.idx == 0 and protocol.include_manual:
                    assert run.contains_binary_content
                    assert run.contains_manual
                    continue

                is_within_window = (
                    len(history.messages_per_run) - run.idx <= preserve_last_frame_for_n_turns
                )
                request = run.messages[0]
                assert isinstance(request, ModelRequest)
                part = request.parts[0]
                assert isinstance(part, UserPromptPart)
                assert isinstance(part.content, list)
                binary_items = [item for item in part.content if isinstance(item, BinaryContent)]
                expected_obs = 1 if is_within_window and num_observations > 0 else 0
                assert len(binary_items) == expected_obs, (
                    f"Expected {expected_obs} observations in turn {run.idx}, got {len(binary_items)}"
                )
                expected_input_tokens = simple_text_response.usage.input_tokens - (
                    (num_observations - expected_obs) * history.token_accountant.tokens_per_image
                )
                assert run.input_tokens == expected_input_tokens


class TestTruncation:
    """Test message history truncation."""

    @parametrize_with_cases("protocol", cases=ProtocolCases)
    def test_no_truncation_when_no_limit(
        self,
        capabilities: PlayerCapabilities,
        protocol: PlayerProtocol,
        model_request: ModelRequest,
        simple_text_response: ModelResponse,
    ) -> None:
        """Test that no truncation occurs when input_tokens_limit is None."""
        history = MessageHistory(capabilities=capabilities, protocol=protocol)

        # Add lots of messages
        for _ in range(10):
            usage = RunUsage(
                requests=1, input_tokens=history.usage.total_tokens + 500, output_tokens=50
            )
            history.update(new_messages=[model_request, simple_text_response], usage=usage)

        history.truncate_history_if_needed()

        # All messages should still be there
        if protocol.include_manual:
            assert len(history) == 11
        else:
            assert len(history) == 10

        # And we should not have truncated at all
        assert history.num_times_truncated == 0

    @parametrize_with_cases("protocol", cases=ProtocolCases)
    def test_no_truncation_when_below_threshold(
        self,
        capabilities: PlayerCapabilities,
        protocol: PlayerProtocol,
        model_request: ModelRequest,
        simple_text_response: ModelResponse,
    ) -> None:
        """Test no truncation when below threshold."""
        caps = capabilities.model_copy(
            update={"usage_limits": replace(capabilities.usage_limits, input_tokens_limit=100000)}
        )
        history = MessageHistory(capabilities=caps, protocol=protocol)

        # Add lots of messages
        for _ in range(10):
            usage = RunUsage(
                requests=1,
                input_tokens=history.usage.total_tokens + simple_text_response.usage.input_tokens,
                output_tokens=50,
            )
            history.update(new_messages=[model_request, simple_text_response], usage=usage)

        history.truncate_history_if_needed()

        # All messages should still be there
        if protocol.include_manual:
            assert len(history) == 11
        else:
            assert len(history) == 10

        # And we should not have truncated at all
        assert history.num_times_truncated == 0

    @parametrize_with_cases("protocol", cases=ProtocolCases)
    def test_truncation_occurs_when_over_threshold(
        self,
        capabilities: PlayerCapabilities,
        protocol: PlayerProtocol,
        model_request: ModelRequest,
        simple_text_response: ModelResponse,
        num_observations: int,
    ) -> None:
        """Test that truncation occurs when over threshold and calculates correctly."""
        if protocol.role == "expert" and num_observations > 0:
            pytest.skip("Skipping expert with observations because that's not allowed to happen")

        # Set a limit with known threshold
        input_limit = 1000 + (num_observations * 1000)
        if protocol.include_manual:
            input_limit += 1000

        caps = capabilities.model_copy(
            update={
                "usage_limits": replace(capabilities.usage_limits, input_tokens_limit=input_limit),
                "max_observations_per_request": num_observations,
            }
        )

        history = MessageHistory(capabilities=caps, protocol=protocol)

        # manually adjust the input tokens for the manual otherwise it's a silly number to test
        # with and its hard to know if it failed or succeeded
        if protocol.include_manual:
            history.messages_per_run[0].input_tokens = 1000
            history.usage.input_tokens = 1000

        for _ in range(50):
            usage = RunUsage(
                requests=1,
                input_tokens=history.usage.total_tokens + simple_text_response.usage.input_tokens,
                output_tokens=simple_text_response.usage.output_tokens,
            )
            history.update(new_messages=[model_request, simple_text_response], usage=usage)

        # Calculate expected state using helper
        initial_length = len(history)
        threshold_tokens = int(input_limit * history.truncation_threshold)

        removable_tokens_per_turn: list[int] = []
        for run in history.messages_per_run:
            if run.contains_manual:
                continue
            removable_tokens_per_turn.append(run.input_tokens + run.output_tokens)

        # Count cumulative token counts per run, but in reverse so we see how many turns to remove
        reverse_cumulative_token_count = list(
            reversed(list(accumulate(reversed(removable_tokens_per_turn))))
        )

        # Figure out what the threshold will be for each of the turns by adding in the margin for
        # new observations and the manual (if any) that we are not deleting.
        additional_token_margin = (
            history.token_accountant.tokens_per_image * caps.max_observations_per_request
        )
        if protocol.include_manual:
            additional_token_margin += history.messages_per_run[0].input_tokens

        # Figure out the number of turns we expect to remove
        for idx, cum_tokens in enumerate(reverse_cumulative_token_count):
            if cum_tokens + additional_token_margin <= threshold_tokens:
                num_turns_to_remove = idx
                break
        else:
            raise AssertionError("Should have found number of turns to remove")

        effective_tokens = history.token_accountant.estimate_next_run_tokens()
        # Verify helper matches what should_truncate says
        assert history.token_accountant.should_truncate(
            threshold=history.truncation_threshold
        ) == (effective_tokens > threshold_tokens)

        # Verify we're over threshold before truncation, so we know that we are going to be
        # truncating something.
        assert effective_tokens > threshold_tokens, (
            f"Should be over threshold: {effective_tokens} > {threshold_tokens} "
            f"(input_tokens={history.usage.input_tokens}, "
            f"image_tokens={history.token_accountant.tokens_per_image * num_observations})"
        )

        history.truncate_history_if_needed()

        # Should have truncated at least one turn
        assert len(history) < initial_length, (
            f"Should have truncated: {len(history)} < {initial_length}"
        )
        assert history.num_times_truncated > 0
        # Make sure we truncate the right number of turns
        assert history.num_times_truncated == num_turns_to_remove

        # Make sure none of the token counts are below 0
        for run in history.messages_per_run:
            assert run.input_tokens > 0
            assert run.output_tokens >= 0

        assert history.usage.input_tokens > 0

        # Make sure we didn't remove the manual
        if protocol.include_manual:
            assert history.messages_per_run[0].contains_manual
