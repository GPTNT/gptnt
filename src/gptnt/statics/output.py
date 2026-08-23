import re
from dataclasses import dataclass, field
from typing import override

from pydantic_ai import AgentRunResult

from gptnt.players.exceptions import AIResponseErrorType
from gptnt.players.reasoning_parser.react import ReactStyleReasoningParser
from gptnt.players.reasoning_parser.reasoning_parser import ReasoningParser, strip_box_envelope
from gptnt.players.result import AgentCallResult

_ACTION_BLOCK = re.compile(r"<action\b[^>]*>(.*?)(?:</action\s*>|$)", re.IGNORECASE | re.DOTALL)
_THOUGHT_BLOCK = re.compile(
    r"<(?:thought|think|thinking)\b[^>]*>.*?</(?:thought|think|thinking)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_THOUGHT_CONTENT = re.compile(
    r"<(?:thought|think|thinking)\b[^>]*>(.*?)</(?:thought|think|thinking)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_UNCLOSED_THOUGHT = re.compile(
    r"<(?:thought|think|thinking)\b[^>]*>.*$", re.IGNORECASE | re.DOTALL
)
_ANSWER_LABEL = re.compile(r"^(?:final\s+answer|answer)\s*[:\-]\s*(.+)$", re.IGNORECASE)
_SINGLE_LETTER_TAG = re.compile(r"^<\s*([a-z])\s*>$", re.IGNORECASE)


def extract_static_answer(response: str) -> str:
    """Extract a native static-task answer, accepting legacy action wrappers too."""
    response = strip_box_envelope(response).strip()

    # Models sometimes mention the required `<action>` wrapper while reasoning. Remove
    # completed reasoning blocks before looking for the real answer so an opening tag inside the
    # reasoning cannot consume everything through the final action's closing tag.
    response_without_thoughts = _THOUGHT_BLOCK.sub("", response)
    action_matches = _ACTION_BLOCK.findall(response_without_thoughts)
    answer = next((match.strip() for match in action_matches if match.strip()), "")
    if not answer:
        answer = response_without_thoughts
        answer = _UNCLOSED_THOUGHT.sub("", answer).strip()

    answer = answer.replace("```json", "").replace("```", "").strip()
    single_letter = _SINGLE_LETTER_TAG.fullmatch(answer)
    if single_letter:
        return single_letter.group(1)

    lines = [line.strip() for line in answer.splitlines() if line.strip()]
    if lines:
        labelled_answer = _ANSWER_LABEL.fullmatch(lines[-1])
        if labelled_answer:
            return labelled_answer.group(1).strip()
    return answer


def static_prediction_answer(output: dict[str, object]) -> str:
    """Return the parsed answer, falling back to raw output from failed legacy parsing."""
    scored_output = output.get("scored_output")
    if isinstance(scored_output, str) and scored_output.strip():
        return scored_output

    parsed_output = output.get("output")
    if isinstance(parsed_output, str) and parsed_output.strip():
        return extract_static_answer(parsed_output)

    raw_output = output.get("raw_output")
    if isinstance(raw_output, str):
        return extract_static_answer(raw_output)
    return ""


@dataclass(kw_only=True)
class StaticsReasoningParser(ReasoningParser[str, str]):
    """Parse optional visible reasoning without requiring gameplay action tags."""

    _legacy_parser: ReactStyleReasoningParser[str] = field(
        default_factory=ReactStyleReasoningParser, repr=False
    )

    @override
    def __call__(
        self, output: AgentRunResult[str], *, output_type: type[str] | None = None
    ) -> AgentCallResult[str]:
        raw_output = output.output
        parsed = self._legacy_parser.parse_react_output(raw_output)
        answer = extract_static_answer(raw_output)

        # Action tags are optional for statics. Other structural errors remain useful
        # diagnostics but do not prevent the answer from being scored.
        ignored_errors = {
            AIResponseErrorType.action_not_present,
            AIResponseErrorType.reasoning_absent,
        }
        if "<action" not in raw_output.lower():
            # The native statics format deliberately places the answer outside the
            # optional thought block, so this gameplay-specific warning is expected.
            ignored_errors.add(AIResponseErrorType.reasoning_mixed_with_untagged_text)
        response_errors = [
            error for error in parsed.response_error_type if error not in ignored_errors
        ]
        thought_blocks = [thought.strip() for thought in _THOUGHT_CONTENT.findall(raw_output)]

        return AgentCallResult(
            output=answer,
            thoughts="\n".join(thought_blocks) or None,
            usage=output.usage,
            new_messages=output.new_messages(),
            ai_response_error=response_errors,
            raw_output=raw_output,
        )
