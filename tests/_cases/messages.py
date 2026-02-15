import datetime

from pydantic_ai import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RequestUsage,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.messages import UserPromptPart
from pytest_cases import fixture, param_fixture
from whenever import Instant

from gptnt.players.ai.tokens import estimate_tokens_for_image_per_model


@fixture
def mock_image_bytes() -> bytes:
    """Mock image bytes (1x1 PNG)."""
    # Minimal valid PNG (1x1 pixel, transparent)
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )


preserve_last_frame_for_n_turns = param_fixture(
    "preserve_last_frame_for_n_turns",
    [0, 1, 3],
    ids=["preserve_obs_0_turns", "preserve_obs_1_turn", "preserve_obs_3_turns"],
)
num_observations = param_fixture(
    "num_observations", [0, 1, 3], ids=["no_obs", "one_obs", "three_obs"]
)


@fixture
def tokens_per_image() -> int:
    """Number of tokens per image observation."""
    return estimate_tokens_for_image_per_model("test", long_side=640, short_side=480)


class ModelMessageCases:
    """Case class for common model message patterns."""

    instruction = "You a good box."
    input_text_tokens = 20

    def case_simple_exchange(
        self, num_observations: int, mock_image_bytes: bytes, tokens_per_image: int
    ) -> list[ModelMessage]:
        """Simple request-response pair with text and image."""
        observations = [
            BinaryContent(data=mock_image_bytes, media_type="image/png")
        ] * num_observations
        return [
            ModelRequest(
                instructions=self.instruction,
                parts=[
                    UserPromptPart(
                        content=[TextPart(content="What is 2+2?"), *observations],
                        timestamp=Instant.now().py_datetime(),
                    )
                ],
            ),
            ModelResponse(
                parts=[TextPart(content="The answer is 4.")],
                timestamp=Instant.now().py_datetime(),
                usage=RequestUsage(
                    input_tokens=self.input_text_tokens + (num_observations * tokens_per_image),
                    output_tokens=50,
                ),
            ),
        ]

    def case_multi_turn_conversation(
        self,
        num_observations: int,
        mock_image_bytes: bytes,
        tokens_per_image: int,
        preserve_last_frame_for_n_turns: int,
    ) -> list[ModelMessage]:
        """Multiple turns of conversation."""
        observations = [[] for _ in range(preserve_last_frame_for_n_turns)]

        for idx, turn in enumerate(observations):
            if idx == len(observations) - 1:
                turn.extend(
                    [BinaryContent(data=mock_image_bytes, media_type="image/png")]
                    * num_observations
                )
            else:
                turn.extend([BinaryContent(data=mock_image_bytes, media_type="image/png")])

        all_requests = [
            ModelRequest(
                instructions=self.instruction,
                parts=[
                    UserPromptPart(
                        content=[TextPart(content="What do you see?"), *turn_observations],
                        timestamp=Instant.now().py_datetime(),
                    )
                ],
            )
            for turn_observations in observations
        ]

        all_responses = []
        # Now we need to make a response for each request, and calculate the usage for each
        # response based on the number of observations included in the dialogue up to that point,
        # making sure to account for the accumulation since the usage is getting bigger for each
        # one.
        for idx, request in enumerate(all_requests):
            num_obs_in_request = sum(
                1
                for part in request.parts
                for content in part.content
                if isinstance(content, BinaryContent)
            )
            previous_usages = sum(response.usage.total_tokens for response in all_responses)
            usage = RequestUsage(
                input_tokens=previous_usages
                + self.input_text_tokens
                + (num_obs_in_request * tokens_per_image),
                output_tokens=50,
            )
            all_responses.append(
                ModelResponse(
                    parts=[TextPart(content=f"Response to turn {idx + 1}.")],
                    timestamp=Instant.now().py_datetime(),
                    usage=usage,
                )
            )

        # Interleave requests and responses to create the full conversation
        conversation = []
        for request, response in zip(all_requests, all_responses, strict=False):
            conversation.append(request)
            conversation.append(response)
        return conversation

    def case_simple_tool_call(self) -> list[ModelMessage]:
        """A simple tool call interaction."""
        return [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content="You should press the red button.",
                        timestamp=datetime.datetime(2025, 12, 4, 19, 30, tzinfo=datetime.UTC),
                    )
                ],
                run_id="123e4567-e89b-12d3-a456-426614174000",
            ),
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="final_result_interact",
                        args='{"action":"click","coordinates":{"x":100,"y":200}}',
                        tool_call_id="call_123",
                    )
                ],
                usage=RequestUsage(input_tokens=100, output_tokens=30),
                model_name="test_model",
                timestamp=datetime.datetime(2025, 1, 1, 12, 0, 1, tzinfo=datetime.UTC),
                provider_name="test_provider",
                finish_reason="tool_call",
                run_id="test-run-001",
            ),
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

    def case_multi_turn_tool_call(self) -> list[ModelMessage]:
        return [
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content="roll down",
                        timestamp=datetime.datetime(
                            2025, 12, 4, 19, 33, 59, 979613, tzinfo=datetime.UTC
                        ),
                    )
                ],
                run_id="3646f60f-ae3c-43cb-82a0-b87025f4c41b",
            ),
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="final_result_InteractGameActionWithThoughtsSingleAlphabetLetter",
                        args='{"action":"down"}',
                        tool_call_id="call_JDbp0oRA7ZgojQoYY121Qw1F",
                    )
                ],
                usage=RequestUsage(
                    input_tokens=343,
                    output_tokens=673,
                    details={
                        "accepted_prediction_tokens": 0,
                        "audio_tokens": 0,
                        "reasoning_tokens": 640,
                        "rejected_prediction_tokens": 0,
                    },
                ),
                model_name="gpt-5-2025-08-07",
                timestamp=datetime.datetime(2025, 12, 4, 19, 34, 3, tzinfo=datetime.UTC),
                provider_name="openai",
                provider_details={"finish_reason": "tool_calls"},
                provider_response_id="chatcmpl-Cj9NTmHlG4ZC17oMWG29pFnInrFGd",
                finish_reason="tool_call",
                run_id="3646f60f-ae3c-43cb-82a0-b87025f4c41b",
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="final_result_InteractGameActionWithThoughtsSingleAlphabetLetter",
                        content="Final result processed.",
                        tool_call_id="call_JDbp0oRA7ZgojQoYY121Qw1F",
                        timestamp=datetime.datetime(
                            2025, 12, 4, 19, 34, 16, 407597, tzinfo=datetime.UTC
                        ),
                    )
                ],
                run_id="3646f60f-ae3c-43cb-82a0-b87025f4c41b",
            ),
            ModelRequest(
                parts=[
                    UserPromptPart(
                        content="roll up now",
                        timestamp=datetime.datetime(
                            2025, 12, 4, 19, 34, 16, 427518, tzinfo=datetime.UTC
                        ),
                    )
                ],
                run_id="514dbb2e-2fb1-47a0-8385-e18a6642e047",
            ),
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="final_result_InteractGameActionWithThoughtsSingleAlphabetLetter",
                        args='{"action":"up"}',
                        tool_call_id="call_bStBnQSSOELOJbyvA5EK6Izk",
                    )
                ],
                usage=RequestUsage(
                    input_tokens=403,
                    output_tokens=545,
                    details={
                        "accepted_prediction_tokens": 0,
                        "audio_tokens": 0,
                        "reasoning_tokens": 512,
                        "rejected_prediction_tokens": 0,
                    },
                ),
                model_name="gpt-5-2025-08-07",
                timestamp=datetime.datetime(2025, 12, 4, 19, 34, 17, tzinfo=datetime.UTC),
                provider_name="openai",
                provider_details={"finish_reason": "tool_calls"},
                provider_response_id="chatcmpl-Cj9NhRZAvEogtizdiG9mCmZ78UMrB",
                finish_reason="tool_call",
                run_id="514dbb2e-2fb1-47a0-8385-e18a6642e047",
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="final_result_InteractGameActionWithThoughtsSingleAlphabetLetter",
                        content="Final result processed.",
                        tool_call_id="call_bStBnQSSOELOJbyvA5EK6Izk",
                        timestamp=datetime.datetime(
                            2025, 12, 4, 19, 34, 32, 590159, tzinfo=datetime.UTC
                        ),
                    )
                ],
                run_id="514dbb2e-2fb1-47a0-8385-e18a6642e047",
            ),
        ]
