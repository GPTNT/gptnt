from dataclasses import dataclass, field
from enum import Enum
from html.parser import HTMLParser
from types import TracebackType
from typing import Any, Literal, Self, cast, override

import structlog
from json_repair import repair_json
from pydantic_ai import AgentRunResult

from gptnt.players.actions import AgentCallResult
from gptnt.players.exceptions import (
    AIResponseErrorType,
    InvalidOutputFormatError,
    ReasoningParsingError,
)
from gptnt.players.reasoning_parser.reasoning_parser import (
    ReasoningParser,
    structure_string_output,
)

logger = structlog.get_logger()

REACT_REASONING_TAG = "thought"
REACT_ACT_TAG = "action"


def _cleanup_string_action_output(output: str) -> str:
    """Clean up actions that are strings best we can."""
    output = output.strip().replace("```json", "").replace("```", "").strip()
    return output


class _UnsetEnum(Enum):
    UNSET = "UNSET"


UnsetType = Literal[_UnsetEnum.UNSET]
UNSET = _UnsetEnum.UNSET
"""Shared sentinel for uninitialized cache values."""


class TagType(Enum):
    """Types of tags."""

    reasoning = "reasoning"
    action = "action"


class TagEvent(Enum):
    """Types of tag events during parsing."""

    opened = "opened"
    closed = "closed"


@dataclass
class TagBlock:
    """Represents a tag block with its type and content."""

    tag: TagType
    event: TagEvent
    position: int
    depth: int


@dataclass
class ContentBlock:
    """Represents a block of content with its type."""

    content: str
    position: int
    depth: int

    tag: TagType | None = None


@dataclass(kw_only=True)
class ParsedReActOutput:
    """Raw parsed data from ReAct-style output.

    Pure data container with basic accessors for reasoning blocks, action blocks, and untagged
    content.
    """

    raw_output: str = ""
    tag_events: list[TagBlock] = field(default_factory=list)
    content_blocks: list[ContentBlock] = field(default_factory=list)

    @property
    def all_events(self) -> list[TagBlock | ContentBlock]:
        """Merge tag events and content blocks, sorted by position."""
        return sorted([*self.tag_events, *self.content_blocks], key=lambda block: block.position)

    @property
    def reasoning_blocks(self) -> list[str]:
        """Extract reasoning blocks from content blocks."""
        return [
            block.content.strip()
            for block in self.content_blocks
            if block.tag == TagType.reasoning and block.content.strip()
        ]

    @property
    def action_blocks(self) -> list[str]:
        """Extract action blocks from content blocks."""
        return [
            block.content.strip()
            for block in self.content_blocks
            if block.tag == TagType.action and block.content.strip()
        ]

    @property
    def untagged_content(self) -> list[str]:
        """Extract untagged content from content blocks."""
        return [
            block.content for block in self.content_blocks if block.tag is None and block.content
        ]


@dataclass(kw_only=True)
class ReActContentExtractor:
    """Extracts thoughts and actions from parsed ReAct output.

    Handles the complex filtering logic for reasoning when multiple actions are present, and
    provides fallback strategies for action extraction with JSON repair.
    """

    parsed: ParsedReActOutput

    _thoughts_cache: str | None | UnsetType = field(default=UNSET, init=False, repr=False)
    _action_cache: str | None | UnsetType = field(default=UNSET, init=False, repr=False)

    @property
    def thoughts(self) -> str | None:
        """Merge reasoning blocks with untagged content, excluding content after actions."""
        if self._thoughts_cache is not UNSET:
            return self._thoughts_cache

        self._thoughts_cache = self._extract_thoughts()
        return self._thoughts_cache

    @property
    def action(self) -> str | None:
        """Extract and process the action with fallback strategies."""
        if self._action_cache is not UNSET:
            return self._action_cache

        self._action_cache = self._extract_action()
        return self._action_cache

    def _extract_thoughts(self) -> str | None:
        """Extract reasoning text, filtering out content after actions."""
        # Get the position of the first closed action tag
        action_close_pos = self._get_first_action_close_position()

        # For multiple actions, get the first action open position
        first_action_open_pos = (
            self._get_first_action_open_position()
            if self._should_filter_reasoning_for_multiple_actions()
            else None
        )

        # Collect all text content (reasoning + untagged) with appropriate filtering
        text_blocks: list[str] = []
        for block in self.parsed.content_blocks:
            # Skip empty
            is_empty_content = not block.content.strip()
            # Skip action blocks
            is_action_block = block.tag == TagType.action

            # Skip content after first action opens (for multiple actions)
            is_content_after_first_action = (
                first_action_open_pos is not None and block.position > first_action_open_pos
            )
            # Skip untagged content that comes after action close (for single action case)
            is_untagged_after_action_close = (
                first_action_open_pos is None
                and block.tag is None
                and action_close_pos is not None
                and block.position > action_close_pos
            )

            if (
                is_empty_content
                or is_action_block
                or is_content_after_first_action
                or is_untagged_after_action_close
            ):
                continue

            # Include reasoning and untagged content (with above filters applied)
            text_blocks.append(block.content.strip())

        merged = "\n".join(text_blocks)
        return merged if merged else None

    def _extract_action(self) -> str | None:
        """Extract action with JSON repair and cleanup fallbacks."""
        # Strategy 1: Use action blocks directly
        potential = next((block for block in self.parsed.action_blocks if block), None)

        # Strategy 2: Fallback to untagged content with JSON repair
        if not potential:
            potential = "\n".join(self.parsed.untagged_content)

        # Try JSON repair if it doesn't look like JSON
        if not potential.startswith("{"):
            repaired = repair_json(potential, skip_json_loads=True).strip()
            potential = repaired if repaired else potential

        potential = _cleanup_string_action_output(potential) if potential else None
        return potential

    def _should_filter_reasoning_for_multiple_actions(self) -> bool:
        """Check if we have multiple actions with reasoning after the first one."""
        if len(self.parsed.action_blocks) <= 1:
            return False

        action_close_pos = self._get_first_action_close_position()

        return bool(
            action_close_pos is not None
            and any(
                tag.tag == TagType.reasoning
                and tag.event == TagEvent.opened
                and tag.position > action_close_pos
                for tag in self.parsed.tag_events
            )
        )

    def _get_first_action_close_position(self) -> int | None:
        """Get the position of the first closed action tag."""
        return next(
            (
                tag.position
                for tag in self.parsed.tag_events
                if tag.tag == TagType.action and tag.event == TagEvent.closed
            ),
            None,
        )

    def _get_first_action_open_position(self) -> int | None:
        """Get the position of the first opened action tag."""
        return next(
            (
                tag.position
                for tag in self.parsed.tag_events
                if tag.tag == TagType.action and tag.event == TagEvent.opened
            ),
            None,
        )


@dataclass
class ReActValidator:
    """Validates parsed ReAct output for structural and content errors.

    Runs independent validators for different error types, with shared position tracking to avoid
    redundant iteration through events.
    """

    parsed: ParsedReActOutput
    extractor: ReActContentExtractor
    maximum_allowed_actions: int = 1
    minimum_expected_reasoning_blocks: int = 1

    # Cached positions to avoid repeated iteration
    _first_reasoning_open_pos: int | None | _UnsetEnum = field(
        default=UNSET, init=False, repr=False
    )
    _first_action_open_pos: int | None | _UnsetEnum = field(default=UNSET, init=False, repr=False)
    _first_action_close_pos: int | None | _UnsetEnum = field(default=UNSET, init=False, repr=False)

    @property
    def errors(self) -> list[AIResponseErrorType]:
        """Run all validators and return aggregated errors."""
        errors: list[AIResponseErrorType] = []

        errors.extend(self._check_missing_reasoning())
        errors.extend(self._check_action_content_errors())
        errors.extend(self._check_ordering_errors())
        errors.extend(self._check_content_after_action())
        errors.extend(self._check_multiple_actions())
        errors.extend(self._check_reasoning_fragmentation())
        errors.extend(self._check_nesting_errors())
        errors.extend(self._check_malformed_tags())

        return errors

    # --- Position Helpers (cached) ---
    def _get_first_reasoning_open_position(self) -> int | None:
        """Get the position of the first opened reasoning tag."""
        if self._first_reasoning_open_pos is not UNSET:
            return self._first_reasoning_open_pos

        self._first_reasoning_open_pos = next(
            (
                tag.position
                for tag in self.parsed.tag_events
                if tag.tag == TagType.reasoning and tag.event == TagEvent.opened
            ),
            None,
        )
        return self._first_reasoning_open_pos

    def _get_first_action_open_position(self) -> int | None:
        """Get the position of the first opened action tag."""
        if self._first_action_open_pos is not UNSET:
            return self._first_action_open_pos

        self._first_action_open_pos = next(
            (
                tag.position
                for tag in self.parsed.tag_events
                if tag.tag == TagType.action and tag.event == TagEvent.opened
            ),
            None,
        )
        return self._first_action_open_pos

    def _get_first_action_close_position(self) -> int | None:
        """Get the position of the first closed action tag."""
        if self._first_action_close_pos is not UNSET:
            return self._first_action_close_pos

        self._first_action_close_pos = next(
            (
                event.position
                for event in self.parsed.tag_events
                if event.tag == TagType.action and event.event == TagEvent.closed
            ),
            None,
        )
        return self._first_action_close_pos

    # --- Error Validators ---
    def _check_missing_reasoning(self) -> list[AIResponseErrorType]:
        """Check if reasoning/thoughts are completely absent."""
        return [AIResponseErrorType.reasoning_absent] if self.extractor.thoughts is None else []

    def _check_action_content_errors(self) -> list[AIResponseErrorType]:
        """Check if action content is missing or empty."""
        errors = []
        has_action_content = bool(self.parsed.action_blocks) and all(
            block.strip() for block in self.parsed.action_blocks
        )

        if not has_action_content:
            errors.append(AIResponseErrorType.action_not_present)

        return errors

    def _check_ordering_errors(self) -> list[AIResponseErrorType]:
        """Check if action appears before reasoning completes."""
        first_reasoning_pos = self._get_first_reasoning_open_position()
        first_action_open_pos = self._get_first_action_open_position()
        first_action_closed_pos = self._get_first_action_close_position()

        if (
            first_action_open_pos is not None
            and first_action_closed_pos is not None
            and first_reasoning_pos is not None
            and first_action_open_pos < first_action_closed_pos < first_reasoning_pos
        ):
            return [AIResponseErrorType.action_placed_before_reasoning]
        return []

    def _check_content_after_action(self) -> list[AIResponseErrorType]:
        """Check if there's content (reasoning or untagged) after action closes."""
        action_close_pos = self._get_first_action_close_position()

        if action_close_pos is not None:
            has_non_action_content_after = any(
                block.position > action_close_pos
                for block in self.parsed.content_blocks
                if block.tag != TagType.action
            )
            has_reasoning_after = any(
                event.tag == TagType.reasoning
                and event.event == TagEvent.opened
                and event.position > action_close_pos
                for event in self.parsed.tag_events
            )
            if has_reasoning_after or has_non_action_content_after:
                return [AIResponseErrorType.content_after_action_complete]
        return []

    def _check_multiple_actions(self) -> list[AIResponseErrorType]:
        """Check if more than the allowed number of actions are present."""
        if len(self.parsed.action_blocks) > self.maximum_allowed_actions:
            return [AIResponseErrorType.multiple_actions_present]
        return []

    def _check_reasoning_fragmentation(self) -> list[AIResponseErrorType]:
        """Check if reasoning is split across multiple blocks or mixed with untagged text."""
        errors = []
        reasoning_opens = sum(
            1
            for event in self.parsed.tag_events
            if event.tag == TagType.reasoning and event.event == TagEvent.opened
        )

        # Check for fragmented reasoning: multiple blocks or multiple opens
        if (
            len(self.parsed.reasoning_blocks) > self.minimum_expected_reasoning_blocks
            or reasoning_opens > 1
        ):
            errors.append(AIResponseErrorType.reasoning_split_across_blocks)

        # Check for reasoning mixed with untagged text specifically
        if self.parsed.untagged_content:
            errors.append(AIResponseErrorType.reasoning_mixed_with_untagged_text)

        return errors

    def _check_nesting_errors(self) -> list[AIResponseErrorType]:
        """Check if tags are improperly nested (action inside reasoning or vice versa)."""
        for event in self.parsed.tag_events:
            # Is there an action block inside this open reasoning block?
            if (
                event.tag == TagType.action
                and event.event == TagEvent.opened
                and self._check_for_improper_nesting(open_tag=event)
            ):
                return [AIResponseErrorType.malformed_tag_structure]

            # Is there a reasoning block inside of this open action block?
            if (
                event.tag == TagType.reasoning
                and event.event == TagEvent.opened
                and self._check_for_improper_nesting(open_tag=event)
            ):
                return [AIResponseErrorType.malformed_tag_structure]
        return []

    def _check_for_improper_nesting(self, *, open_tag: TagBlock) -> bool:  # noqa: WPS231
        tag_type = open_tag.tag
        opposite_tag = TagType.action if tag_type == TagType.reasoning else TagType.reasoning

        # Check if the other tag is open at the start of this tag
        depth_at_start = sum(
            1 if event.event == TagEvent.opened else -1
            for event in self.parsed.tag_events
            if event.position < open_tag.position and event.tag == opposite_tag
        )

        if depth_at_start <= 0:
            return False

        depth = 1

        for next_e in self.parsed.tag_events:
            is_event_before_open_tag = next_e.position <= open_tag.position
            is_next_event_not_same_type = next_e.tag != tag_type

            if is_event_before_open_tag or is_next_event_not_same_type:
                continue

            match next_e.event:
                case TagEvent.opened:
                    depth += 1
                case TagEvent.closed:
                    depth -= 1

            if depth == 0:
                # Check if the other tag is still open at this close
                depth_at_close = sum(
                    1 if event.event == TagEvent.opened else -1
                    for event in self.parsed.tag_events
                    if event.position <= next_e.position and event.tag == opposite_tag
                )
                return depth_at_close > 0

        return False

    def _check_malformed_tags(self) -> list[AIResponseErrorType]:
        """Check for unmatched opening/closing tags."""
        reasoning_opens_count = sum(
            1
            for event in self.parsed.tag_events
            if event.tag == TagType.reasoning and event.event == TagEvent.opened
        )
        reasoning_closes_count = sum(
            1
            for event in self.parsed.tag_events
            if event.tag == TagType.reasoning and event.event == TagEvent.closed
        )
        action_opens_count = sum(
            1
            for event in self.parsed.tag_events
            if event.tag == TagType.action and event.event == TagEvent.opened
        )
        action_closes_count = sum(
            1
            for event in self.parsed.tag_events
            if event.tag == TagType.action and event.event == TagEvent.closed
        )

        if (
            reasoning_opens_count != reasoning_closes_count
            or action_opens_count != action_closes_count
        ):
            return [AIResponseErrorType.malformed_tag_structure]
        return []


@dataclass(kw_only=True)
class ReactParseResult:
    """Result of parsing ReAct-style output.

    Facade class that delegates to specialized components for extraction and validation. Maintains
    backward compatibility with existing tests and usage.
    """

    maximum_allowed_actions: int = 1
    minimum_expected_reasoning_blocks: int = 1

    raw_output: str = ""
    tag_events: list[TagBlock] = field(default_factory=list)
    content_blocks: list[ContentBlock] = field(default_factory=list)

    # Lazy-initialized components
    _parsed: ParsedReActOutput | None = field(default=None, init=False, repr=False)
    _extractor: ReActContentExtractor | None = field(default=None, init=False, repr=False)
    _validator: ReActValidator | None = field(default=None, init=False, repr=False)

    @property
    def parsed(self) -> ParsedReActOutput:
        """Get or create the parsed data container."""
        if self._parsed is None:
            self._parsed = ParsedReActOutput(
                raw_output=self.raw_output,
                tag_events=self.tag_events,
                content_blocks=self.content_blocks,
            )
        return self._parsed

    @property
    def extractor(self) -> ReActContentExtractor:
        """Get or create the content extractor."""
        if self._extractor is None:
            self._extractor = ReActContentExtractor(parsed=self.parsed)
        return self._extractor

    @property
    def validator(self) -> ReActValidator:
        """Get or create the validator."""
        if self._validator is None:
            self._validator = ReActValidator(
                self.parsed,
                self.extractor,
                maximum_allowed_actions=self.maximum_allowed_actions,
                minimum_expected_reasoning_blocks=self.minimum_expected_reasoning_blocks,
            )
        return self._validator

    @property
    def thoughts(self) -> str | None:
        """Merge reasoning blocks with untagged content."""
        return self.extractor.thoughts

    @property
    def action(self) -> str | None:
        """Extract and process the action from parsing results."""
        return self.extractor.action

    @property
    def response_error_type(self) -> list[AIResponseErrorType]:
        """Detect parsing and structural errors in the output."""
        return self.validator.errors


class ReactTagOutputParser(HTMLParser):
    """Parse ReAct-style output with reasoning and action tags.

    We use HTMLParser to figure out what is reasoning and what is the action, if they exist.
    """

    def __init__(
        self, *, reasoning_tag: str = REACT_REASONING_TAG, act_tag: str = REACT_ACT_TAG
    ) -> None:
        # Auto-convert HTML entities
        super().__init__(convert_charrefs=True)
        self.reasoning_tag = reasoning_tag.lower()
        self.act_tag = act_tag.lower()

        # State tracking
        self._reasoning_depth = 0
        self._action_depth = 0
        self._current_reasoning: list[str] = []
        self._current_action: list[str] = []
        self._outside_content: list[str] = []
        self._event_counter = 0

        self.output = ReactParseResult()

    def __enter__(self) -> Self:
        """Enter context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit context manager."""
        self.close()

    @override
    def feed(self, data: str) -> None:
        # Store the raw output in the parsed result in case we need it
        self.output.raw_output += data
        # Then just run the parser
        super().feed(data)

    @override
    def handle_starttag(self, tag: str, attrs: list[Any]) -> None:
        """Handle opening tags."""
        tag = tag.lower()

        # If we know we are about to move another depth or tag, store what we have
        if tag in {self.reasoning_tag, self.act_tag}:
            self._store_content()

        match tag:
            case self.reasoning_tag:
                self._reasoning_depth += 1
                self._record_tag_event(TagType.reasoning, TagEvent.opened, self._reasoning_depth)
            case self.act_tag:
                self._action_depth += 1
                self._record_tag_event(TagType.action, TagEvent.opened, self._action_depth)
            case _:
                # Preserve markup for unrecognised tags
                if self._reasoning_depth > 0:
                    self._current_reasoning.append(f"<{tag}>")
                elif self._action_depth > 0:
                    self._current_action.append(f"<{tag}>")

    @override
    def handle_endtag(self, tag: str) -> None:
        """Handle closing tags."""
        tag = tag.lower()

        # If we know we are about to move another depth or tag, store what we have
        if tag in {self.reasoning_tag, self.act_tag}:
            self._store_content()

        match tag:
            case self.reasoning_tag:
                self._record_tag_event(TagType.reasoning, TagEvent.closed, self._reasoning_depth)
                self._reasoning_depth = max(0, self._reasoning_depth - 1)
            case self.act_tag:
                self._record_tag_event(TagType.action, TagEvent.closed, self._action_depth)
                self._action_depth = max(0, self._action_depth - 1)
            case "root":
                return
            case _:
                # Preserve markup for unrecognised tags
                if self._reasoning_depth > 0:
                    self._current_reasoning.append(f"</{tag}>")
                elif self._action_depth > 0:
                    self._current_action.append(f"</{tag}>")

    @override
    def handle_data(self, data: str) -> None:
        """Handle text content with routing logic."""
        if not data.strip():
            return

        # Direct child of reasoning tag
        if self._reasoning_depth > 0 and self.lasttag == self.reasoning_tag:
            self._current_reasoning.append(data)
            return

        # Direct child of action tag
        if self._action_depth > 0 and self.lasttag == self.act_tag:
            self._current_action.append(data)
            return

        # Not direct child - check for JSON auto-detection for action
        repaired = repair_json(data, skip_json_loads=True).strip()
        if repaired:
            self._current_action.append(repaired)
            return

        # Text outside of any tag - route based on context
        if self._reasoning_depth > 0:
            # Inside reasoning tag (but not direct child)
            self._current_reasoning.append(data)
        elif self._action_depth > 0:
            # Inside action tag (but not direct child)
            self._current_action.append(data)
        else:
            # Completely outside any tags
            self._outside_content.append(data)

    @override
    def close(self) -> None:
        """Finalize parsing by handling unclosed tags and outside content."""
        super().close()

        self._store_content()

    def _store_content(self) -> None:
        # Handle unclosed tags by recording accumulated content
        # Note: We do NOT add implicit close events here to preserve detection of malformed tags
        if self._current_reasoning:
            content = "".join(self._current_reasoning).strip()
            if content:
                self._record_content(content, TagType.reasoning, self._reasoning_depth or 1)
                self._current_reasoning = []

        if self._current_action:
            content = "".join(self._current_action).strip()
            if content:
                self._record_content(content, TagType.action, self._action_depth or 1)
                self._current_action = []

        for content in self._outside_content:
            self._record_content(content, tag=None, depth=0)
            self._outside_content = []

    def _record_tag_event(self, tag: TagType, event: TagEvent, depth: int) -> None:
        """Record a tag opening/closing event."""
        self.output.tag_events.append(
            TagBlock(tag=tag, event=event, position=self._event_counter, depth=depth)
        )
        self._event_counter += 1

    def _record_content(self, content: str, tag: TagType | None = None, depth: int = 0) -> None:
        """Record content block."""
        if content.strip():
            self.output.content_blocks.append(
                ContentBlock(content=content, position=self._event_counter, depth=depth, tag=tag)
            )
            self._event_counter += 1


@dataclass(kw_only=True)
class ReactStyleReasoningParser[OutputT](ReasoningParser[str, OutputT]):
    """Parser for React-style reasoning.

    Here, the reasoning is part of the normal message flow.
    """

    reasoning_tag: str = REACT_REASONING_TAG
    act_tag: str = REACT_ACT_TAG

    @override
    def __call__(
        self, output: AgentRunResult[str], *, output_type: type[OutputT] | None = None
    ) -> AgentCallResult[OutputT]:
        parsed = self.parse_react_output(output.output)

        if not parsed.action:
            assert parsed.response_error_type is not None
            raise ReasoningParsingError(
                output=output.output,
                expected_type=output_type,
                response_error=parsed.response_error_type,
            )

        # Support optional structuring if output_type is provided otherwise we just return as is
        # (which is a string)
        structured_action = cast("OutputT", parsed.action)
        if output_type is not None:
            try:
                structured_action = structure_string_output(
                    output=parsed.action, output_type=output_type
                )
            except InvalidOutputFormatError as err:
                # If the action content can't be structured/parsed, raise an error with action_parsing_failed
                raise ReasoningParsingError(
                    output=output.output,
                    expected_type=output_type,
                    response_error=[
                        *parsed.response_error_type,
                        AIResponseErrorType.action_parsing_failed,
                    ],
                ) from err

        return AgentCallResult(
            output=structured_action,
            thoughts=parsed.thoughts,
            usage=output.usage(),
            new_messages=output.new_messages(),
            ai_response_error=parsed.response_error_type,
            raw_output=output.output,
        )

    def parse_react_output(self, model_output: str) -> ReactParseResult:
        """Parse ReAct-style output using HTMLParser."""
        parser = ReactTagOutputParser(reasoning_tag=self.reasoning_tag, act_tag=self.act_tag)
        with parser:
            model_output = f"<root>{model_output}</root>"
            parser.feed(model_output)

        return parser.output
