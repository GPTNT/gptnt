from contextlib import ExitStack
from typing import NamedTuple

import pytest
from pydantic_ai import Agent, ModelMessage, ModelResponse, TextPart, ThinkingPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pytest_cases import fixture, param_fixture, parametrize_with_cases
from tests.players.ai.conftest import SuccessfulOutputCases

from gptnt.players.actions import (
    AbsoluteCoordinate,
    InteractGameAction,
    PlayerOutputType,
    SendMessageAction,
)
from gptnt.players.exceptions import AIResponseErrorType, ReasoningParsingError
from gptnt.players.reasoning_parser.inner_monologue import InnerMonologueReasoningParser
from gptnt.players.reasoning_parser.react import (
    REACT_ACT_TAG,
    REACT_REASONING_TAG,
    ReactStyleReasoningParser,
)
from gptnt.players.specification import PlayerCapabilities, PlayerDeps, PlayerProtocol

thinking_output = param_fixture(
    "thinking_output", [None, "This is my inner monologue."], ids=["no_thinking", "with_thinking"]
)


class ParsedOutputCase(NamedTuple):
    action: PlayerOutputType | None
    thoughts: str | None
    exception: type[Exception] | None
    model_output_text: str
    error_type: set[AIResponseErrorType]


class CapabilitiesCases:
    def case_prompted_set_of_marks(self) -> PlayerCapabilities:
        return PlayerCapabilities(
            player_name="test_player",
            player_type="ai",
            structured_output_mode="prompted",
            interaction_location_method="set-of-marks",
            thinking_method="inner-monologue",
        )

    def case_prompted_coordinates(self) -> PlayerCapabilities:
        return PlayerCapabilities(
            player_name="test_player",
            player_type="ai",
            structured_output_mode="prompted",
            interaction_location_method="coordinates",
            thinking_method="inner-monologue",
        )

    def case_react_set_of_marks(self) -> PlayerCapabilities:
        return PlayerCapabilities(
            player_name="test_player",
            player_type="ai",
            structured_output_mode=None,
            interaction_location_method="set-of-marks",
            thinking_method="thinking-out-loud",
        )

    def case_react_coordinates(self) -> PlayerCapabilities:
        return PlayerCapabilities(
            player_name="test_player",
            player_type="ai",
            structured_output_mode=None,
            interaction_location_method="coordinates",
            thinking_method="thinking-out-loud",
        )


@fixture
def protocol() -> PlayerProtocol:
    return PlayerProtocol(
        role="defuser",
        communication_style="sync",
        is_playing_alone=False,
        include_manual=True,
        receive_feedback_after_action=False,
        allow_magic_actions=False,
    )


@parametrize_with_cases("capabilities", cases=CapabilitiesCases, glob="*prompted*")
@parametrize_with_cases("expected_output", cases=SuccessfulOutputCases)
def test_inner_monologue_reasoning_parser(
    protocol: PlayerProtocol,
    capabilities: PlayerCapabilities,
    expected_output: PlayerOutputType | str,
    thinking_output: str | None,
) -> None:
    invalid_test_combinations = [
        (
            capabilities.interaction_location_method == "coordinates"
            and isinstance(expected_output, InteractGameAction)
            and not isinstance(expected_output.location, AbsoluteCoordinate)
        ),
        (
            capabilities.interaction_location_method == "set-of-marks"
            and isinstance(expected_output, InteractGameAction)
            and not isinstance(expected_output.location, (str, int))
        ),
    ]
    if any(invalid_test_combinations):
        pytest.skip("Skip invalid test case")

    # init the model
    def _inner_monologue_function_model(  # noqa: WPS430
        messages: list[ModelMessage],  # noqa: ARG001
        info: AgentInfo,  # noqa: ARG001
    ) -> ModelResponse:
        response_parts = [
            TextPart(
                content=expected_output.text_part_dump()  # noqa: WPS504
                if not isinstance(expected_output, str)
                else expected_output
            )
        ]
        if thinking_output is not None:
            response_parts.insert(0, ThinkingPart(content=thinking_output))
        return ModelResponse(parts=response_parts)

    deps = PlayerDeps(capabilities=capabilities, protocol=protocol)
    agent = Agent(FunctionModel(_inner_monologue_function_model), deps_type=PlayerDeps, retries=0)

    # we need to get a model output
    run_result = agent.run_sync("hi", deps=deps, output_type=deps.output_type)

    parsed_output = InnerMonologueReasoningParser()(run_result, output_type=deps.output_type)

    assert parsed_output.output == expected_output
    assert parsed_output.thoughts == thinking_output


@parametrize_with_cases("capabilities", cases=CapabilitiesCases, glob="*react*")
@parametrize_with_cases("expected_output", cases=SuccessfulOutputCases)
def test_react_reasoning_parser_with_success(
    capabilities: PlayerCapabilities,
    protocol: PlayerProtocol,
    expected_output: PlayerOutputType | str,
    thinking_output: str | None,
) -> None:
    invalid_test_combinations = [
        (
            capabilities.interaction_location_method == "coordinates"
            and isinstance(expected_output, InteractGameAction)
            and not isinstance(expected_output.location, AbsoluteCoordinate)
        ),
        (
            capabilities.interaction_location_method == "set-of-marks"
            and isinstance(expected_output, InteractGameAction)
            and not isinstance(expected_output.location, (str, int))
        ),
    ]
    if any(invalid_test_combinations):
        pytest.skip("Skip invalid test case")

    action_as_string = (
        expected_output.text_part_dump()  # noqa: WPS504
        if not isinstance(expected_output, str)
        else expected_output
    )
    output_text = f"<{REACT_ACT_TAG}>{action_as_string}</{REACT_ACT_TAG}>"
    if thinking_output is not None:
        output_text = (
            f"<{REACT_REASONING_TAG}>{thinking_output}</{REACT_REASONING_TAG}>\n{output_text}"
        )

    deps = PlayerDeps(capabilities=capabilities, protocol=protocol)
    agent = Agent(TestModel(custom_output_text=output_text), deps_type=PlayerDeps, retries=0)

    # we need to get a model output
    run_result = agent.run_sync("hi", deps=deps, output_type=deps.output_type)

    parsed_output = ReactStyleReasoningParser()(
        run_result, output_type=deps.structured_output_type
    )

    assert parsed_output.output == expected_output
    assert parsed_output.thoughts == thinking_output


class BadReactOutputCases:
    """Cases checking for parsing edge-cases and failures.

    Note that all the cases here use SendMessageAction to simplify the test below.
    """

    thoughts = "Thoughts."

    @property
    def action(self) -> SendMessageAction:
        return SendMessageAction(message="Hello")

    def case_only_reasoning(self) -> ParsedOutputCase:
        """Only reasoning tag, no action at all."""
        output = f"<{REACT_REASONING_TAG}>{self.thoughts}</{REACT_REASONING_TAG}>"
        return ParsedOutputCase(
            action=None,
            thoughts=self.thoughts,
            exception=ReasoningParsingError,
            model_output_text=output,
            error_type={AIResponseErrorType.action_not_present},
        )

    def case_only_action(self) -> ParsedOutputCase:
        """Only action tag, no reasoning at all."""
        output = f"<{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts=None,
            exception=None,
            model_output_text=output,
            error_type={AIResponseErrorType.reasoning_absent},
        )

    def case_no_action_tags(self) -> ParsedOutputCase:
        """Reasoning in tags, action without tags - parser handles gracefully."""
        output = f"<{REACT_REASONING_TAG}>{self.thoughts}</{REACT_REASONING_TAG}>\n{self.action.text_part_dump()}"
        return ParsedOutputCase(
            action=self.action,
            thoughts=self.thoughts,
            exception=None,
            model_output_text=output,
            error_type=set(),
        )

    def case_only_action_no_tags(self) -> ParsedOutputCase:
        """Action without any tags, no reasoning present."""
        output = self.action.text_part_dump()
        return ParsedOutputCase(
            action=self.action,
            thoughts=None,
            exception=None,
            model_output_text=output,
            error_type={AIResponseErrorType.reasoning_absent},
        )

    def case_only_reasoning_open_tag(self) -> ParsedOutputCase:
        """Reasoning tag opened but never closed, no action generated."""
        output = f"<{REACT_REASONING_TAG}>{self.thoughts}"
        return ParsedOutputCase(
            action=None,
            thoughts=None,
            exception=ReasoningParsingError,
            model_output_text=output,
            error_type={
                AIResponseErrorType.malformed_tag_structure,
                AIResponseErrorType.action_not_present,
            },
        )

    def case_unclosed_action_tag(self) -> ParsedOutputCase:
        """Action tag opened but never closed - parser still extracts action."""
        output = f"<{REACT_REASONING_TAG}>{self.thoughts}</{REACT_REASONING_TAG}>\n<{REACT_ACT_TAG}>{self.action.text_part_dump()}"
        return ParsedOutputCase(
            action=self.action,
            thoughts=self.thoughts,
            exception=None,
            model_output_text=output,
            error_type={AIResponseErrorType.malformed_tag_structure},
        )

    def case_empty_reasoning(self) -> ParsedOutputCase:
        """Empty reasoning tag - no reasoning content."""
        output = f"<{REACT_REASONING_TAG}></{REACT_REASONING_TAG}>\n<{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts=None,
            exception=None,
            model_output_text=output,
            error_type={AIResponseErrorType.reasoning_absent},
        )

    def case_empty_action(self) -> ParsedOutputCase:
        """Empty action tag - no action content to parse."""
        output = f"<{REACT_REASONING_TAG}>{self.thoughts}</{REACT_REASONING_TAG}>\n<{REACT_ACT_TAG}></{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=None,
            thoughts=self.thoughts,
            exception=ReasoningParsingError,
            model_output_text=output,
            error_type={AIResponseErrorType.action_not_present},
        )

    def case_whitespace_only_reasoning(self) -> ParsedOutputCase:
        """Reasoning tag with only whitespace - effectively no reasoning."""
        output = f"<{REACT_REASONING_TAG}>   \n\t  </{REACT_REASONING_TAG}>\n<{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts=None,
            exception=None,
            model_output_text=output,
            error_type={AIResponseErrorType.reasoning_absent},
        )

    @pytest.mark.skip(reason="This is handled by Pydantic-AI itself")
    def case_empty_output(self) -> ParsedOutputCase:
        """Completely empty output - nothing generated."""
        return ParsedOutputCase(
            action=None,
            thoughts=None,
            exception=ReasoningParsingError,
            model_output_text="",
            error_type={
                AIResponseErrorType.action_not_present,
                AIResponseErrorType.reasoning_absent,
            },
        )

    def case_whitespace_only_output(self) -> ParsedOutputCase:
        """Output with only whitespace - effectively empty."""
        output = "   \n\n\t  "
        return ParsedOutputCase(
            action=None,
            thoughts=None,
            exception=ReasoningParsingError,
            model_output_text=output,
            error_type={
                AIResponseErrorType.reasoning_absent,
                AIResponseErrorType.action_not_present,
            },
        )

    def case_wrong_tag_order(self) -> ParsedOutputCase:
        """Action appears before reasoning - incorrect ordering."""
        output = f"<{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>\n<{REACT_REASONING_TAG}>{self.thoughts}</{REACT_REASONING_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts=self.thoughts,
            exception=None,
            model_output_text=output,
            error_type={
                AIResponseErrorType.action_placed_before_reasoning,
                AIResponseErrorType.content_after_action_complete,
            },
        )

    def case_multiple_actions(self) -> ParsedOutputCase:
        """Multiple action tags when only one is expected."""
        first_action = SendMessageAction(message="First")
        second_action = SendMessageAction(message="Second")
        output = f"<{REACT_REASONING_TAG}>{self.thoughts}</{REACT_REASONING_TAG}>\n<{REACT_ACT_TAG}>{first_action.text_part_dump()}</{REACT_ACT_TAG}>\n<{REACT_ACT_TAG}>{second_action.text_part_dump()}</{REACT_ACT_TAG}>"

        return ParsedOutputCase(
            action=first_action,
            thoughts=self.thoughts,
            exception=None,
            model_output_text=output,
            error_type={AIResponseErrorType.multiple_actions_present},
        )

    def case_multiple_reasoning(self) -> ParsedOutputCase:
        """Multiple reasoning tags - reasoning split across separate blocks."""
        first_thought = "First thought."
        second_thought = "Second thought."
        output = f"<{REACT_REASONING_TAG}>{first_thought}</{REACT_REASONING_TAG}>\n<{REACT_REASONING_TAG}>{second_thought}</{REACT_REASONING_TAG}>\n<{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts=f"{first_thought}\n{second_thought}",
            exception=None,
            model_output_text=output,
            error_type={AIResponseErrorType.reasoning_split_across_blocks},
        )

    def case_malformed_action_content(self) -> ParsedOutputCase:
        """Action tag with malformed/invalid action data that can't be parsed."""
        output = f"<{REACT_REASONING_TAG}>{self.thoughts}</{REACT_REASONING_TAG}>\n<{REACT_ACT_TAG}>not valid action data</{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=None,
            thoughts=self.thoughts,
            exception=ReasoningParsingError,
            model_output_text=output,
            error_type={AIResponseErrorType.action_parsing_failed},
        )

    def case_mismatched_closing_tag(self) -> ParsedOutputCase:
        """Opening and closing tags don't match - parser is lenient and extracts content."""
        output = f"<{REACT_REASONING_TAG}>Thinking.</wrong_tag>\n<{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts="Thinking.</wrong_tag>",
            exception=None,
            model_output_text=output,
            error_type={AIResponseErrorType.malformed_tag_structure},
        )

    def case_mismatched_opening_tag(self) -> ParsedOutputCase:
        """Unexpected tag appears mid-content - parser is lenient."""
        output = f"<{REACT_REASONING_TAG}>Thinking.<wrong_tag>\n<{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts="Thinking.<wrong_tag>",
            exception=None,
            model_output_text=output,
            error_type={AIResponseErrorType.malformed_tag_structure},
        )

    def case_nested_tags_with_invalid_action(self) -> ParsedOutputCase:
        """Incorrectly nested tags with action that can't be parsed."""
        output = f"<{REACT_REASONING_TAG}><{REACT_ACT_TAG}>Nested content</{REACT_ACT_TAG}></{REACT_REASONING_TAG}>"
        return ParsedOutputCase(
            action=None,
            thoughts=None,
            exception=ReasoningParsingError,
            model_output_text=output,
            error_type={
                AIResponseErrorType.malformed_tag_structure,
                AIResponseErrorType.reasoning_absent,
                AIResponseErrorType.action_parsing_failed,
            },
        )

    def case_nested_tags_with_valid_action(self) -> ParsedOutputCase:
        """Action nested inside reasoning tag - structurally incorrect but action is parseable."""
        output = f"<{REACT_REASONING_TAG}><{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}></{REACT_REASONING_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts=None,
            exception=None,
            model_output_text=output,
            error_type={
                AIResponseErrorType.malformed_tag_structure,
                AIResponseErrorType.reasoning_absent,
            },
        )

    def case_text_outside_tags(self) -> ParsedOutputCase:
        """Valid tags but with unexpected text outside them - reasoning mixed with untagged content."""
        output = f"Random text\n<{REACT_REASONING_TAG}>Thinking.</{REACT_REASONING_TAG}>\nMore random text\n<{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts="Random text\nThinking.\nMore random text",
            exception=None,
            model_output_text=output,
            error_type={AIResponseErrorType.reasoning_mixed_with_untagged_text},
        )

    def case_action_with_text_before_and_after(self) -> ParsedOutputCase:
        """Text before and after valid action tag - reasoning contaminated and content after action."""
        before_text = "Some preamble"
        after_text = "Some conclusion"
        output = f"{before_text}\n<{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>\n{after_text}"
        return ParsedOutputCase(
            action=self.action,
            thoughts=before_text,
            exception=None,
            model_output_text=output,
            error_type={
                AIResponseErrorType.reasoning_mixed_with_untagged_text,
                AIResponseErrorType.content_after_action_complete,
            },
        )

    def case_multiple_unclosed_reasoning_with_valid_action(self) -> ParsedOutputCase:
        """Multiple unclosed reasoning tags but valid action - both structural and fragmentation issues."""
        first_thinking = "First"
        second_thinking = "Second"
        output = f"<{REACT_REASONING_TAG}>{first_thinking}\n<{REACT_REASONING_TAG}>{second_thinking}\n<{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts=f"{first_thinking}\n{second_thinking}",
            exception=None,
            model_output_text=output,
            error_type={
                AIResponseErrorType.malformed_tag_structure,
                AIResponseErrorType.reasoning_split_across_blocks,
            },
        )

    def case_reasoning_after_action(self) -> ParsedOutputCase:
        """Reasoning appears after action is complete - wrong order and fragmented."""
        output = f"<{REACT_REASONING_TAG}>Thinking.</{REACT_REASONING_TAG}>\n<{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>\n<{REACT_REASONING_TAG}>More thinking.</{REACT_REASONING_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts="Thinking.\nMore thinking.",
            exception=None,
            model_output_text=output,
            error_type={
                AIResponseErrorType.content_after_action_complete,
                AIResponseErrorType.reasoning_split_across_blocks,
            },
        )

    def case_reasoning_around_action(self) -> ParsedOutputCase:
        """Reasoning tag wraps around action - action generated before reasoning complete and reasoning fragmented."""
        output = f"<{REACT_REASONING_TAG}>Thinking.\n<{REACT_ACT_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>\nMore thinking.</{REACT_REASONING_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts="Thinking.\nMore thinking.",
            exception=None,
            model_output_text=output,
            error_type={
                # AIResponseErrorType.action_placed_before_reasoning,
                AIResponseErrorType.content_after_action_complete,
                AIResponseErrorType.malformed_tag_structure,
                AIResponseErrorType.reasoning_split_across_blocks,
            },
        )

    def case_interleaved_reasoning_and_actions(self) -> ParsedOutputCase:
        """Reasoning, action, reasoning, action pattern - multiple violations."""
        first_action = SendMessageAction(message="First").text_part_dump()
        second_action = SendMessageAction(message="Second").text_part_dump()
        output = f"<{REACT_REASONING_TAG}>First.</{REACT_REASONING_TAG}>\n<{REACT_ACT_TAG}>{first_action}</{REACT_ACT_TAG}>\n<{REACT_REASONING_TAG}>Second.</{REACT_REASONING_TAG}>\n<{REACT_ACT_TAG}>{second_action}</{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=SendMessageAction(message="First"),
            thoughts="First.",
            exception=None,
            model_output_text=output,
            error_type={
                AIResponseErrorType.multiple_actions_present,
                AIResponseErrorType.reasoning_split_across_blocks,
                AIResponseErrorType.content_after_action_complete,
            },
        )

    def case_action_only_opening_tag_no_content(self) -> ParsedOutputCase:
        """Action opening tag but no content or closing tag - malformed and no action."""
        output = f"<{REACT_REASONING_TAG}>Thinking.</{REACT_REASONING_TAG}>\n<{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=None,
            thoughts="Thinking.",
            exception=ReasoningParsingError,
            model_output_text=output,
            error_type={
                AIResponseErrorType.malformed_tag_structure,
                AIResponseErrorType.action_not_present,
            },
        )

    def case_reasoning_nested_in_action(self) -> ParsedOutputCase:
        """Reasoning tag nested inside action tag - malformed tag structure."""
        output = f"<{REACT_ACT_TAG}><{REACT_REASONING_TAG}>Thinking</{REACT_REASONING_TAG}>{self.action.text_part_dump()}</{REACT_ACT_TAG}>"
        return ParsedOutputCase(
            action=self.action,
            thoughts="Thinking",
            exception=None,
            model_output_text=output,
            error_type={AIResponseErrorType.malformed_tag_structure},
        )


@parametrize_with_cases("capabilities", cases=CapabilitiesCases, glob="*react*")
@parametrize_with_cases("expected_output", cases=BadReactOutputCases)
def test_react_reasoning_parser_with_failures(
    capabilities: PlayerCapabilities, protocol: PlayerProtocol, expected_output: ParsedOutputCase
) -> None:
    deps = PlayerDeps(capabilities=capabilities, protocol=protocol)
    agent = Agent(
        TestModel(custom_output_text=expected_output.model_output_text),
        deps_type=PlayerDeps,
        retries=0,
    )

    # we need to get a model output
    run_result = agent.run_sync("hi", deps=deps, output_type=deps.output_type)
    with ExitStack() as stack:
        exc_info = None
        if expected_output.exception is not None:
            exc_info = stack.enter_context(pytest.raises(expected_output.exception))

        parsed_output = ReactStyleReasoningParser()(
            run_result, output_type=deps.structured_output_type
        )

        assert parsed_output.output == expected_output.action
        assert parsed_output.thoughts == expected_output.thoughts
        assert set(parsed_output.ai_response_error) == expected_output.error_type

    if expected_output.exception is not None:
        assert exc_info is not None
        assert exc_info.type == expected_output.exception
        assert isinstance(exc_info.value, ReasoningParsingError)
        assert set(exc_info.value.response_error) == expected_output.error_type
