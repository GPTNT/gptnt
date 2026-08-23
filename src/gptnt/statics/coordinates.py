from collections.abc import Iterator
from typing import Any, Literal, Self

import json_repair
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic_ai import NativeOutput, PromptedOutput, ToolOutput

from gptnt.players.specification import PlayerCapabilities


class Coords(BaseModel):
    """A pixel coordinate."""

    model_config = ConfigDict(extra="forbid")

    x: int  # noqa: WPS111
    y: int  # noqa: WPS111

    def is_in_bounds(self, width: int, height: int) -> bool:
        """Check if the coordinates are within the bounds."""
        return 0 <= self.x <= width and 0 <= self.y <= height


class CoordinateModelOutput(BaseModel):
    """Validated object contract for coordinate and non-coordinate grounding answers."""

    model_config = ConfigDict(extra="forbid")

    x: int | None = None  # noqa: WPS111
    y: int | None = None  # noqa: WPS111
    answer: Literal["More information needed", "None"] | None = None

    @model_validator(mode="after")
    def validate_coordinate_or_answer(self) -> Self:
        """Require exactly one complete coordinate pair or one sentinel answer."""
        has_coordinate = self.x is not None and self.y is not None
        has_partial_coordinate = (self.x is None) != (self.y is None)
        if has_partial_coordinate or has_coordinate == (self.answer is not None):
            raise ValueError("Return either both x and y, or answer, but not both.")
        return self


def coordinate_model_output_type(capabilities: PlayerCapabilities) -> Any:
    """Build the coordinate task's output contract for the configured provider mode."""
    match capabilities.structured_output_mode:
        case "native":
            return NativeOutput(CoordinateModelOutput)
        case "tool":
            return ToolOutput(CoordinateModelOutput)
        case "prompted":
            return PromptedOutput(CoordinateModelOutput)
        case None:
            return str


def serialise_coordinate_model_output(output: Any) -> str:
    """Serialize a validated coordinate-task response for storage and scoring."""
    if isinstance(output, CoordinateModelOutput):
        if output.answer is not None:
            return output.answer
        assert output.x is not None
        assert output.y is not None
        return Coords(x=output.x, y=output.y).model_dump_json()
    return str(output)


def _iter_json_objects(output: str) -> Iterator[str]:  # noqa: WPS231
    """Yield every balanced JSON-object-shaped substring in source order."""
    stack: list[int] = []
    ranges: list[tuple[int, int]] = []
    in_string = False
    escaped = False

    for index, character in enumerate(output):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character == "{":
            stack.append(index)
        elif character == "}" and stack:
            ranges.append((stack.pop(), index + 1))

    for start, end in sorted(ranges):
        yield output[start:end]


def select_coordinate_candidate(output: str) -> str:
    """Select the first valid coordinate, or the final candidate if none are valid."""
    candidates = list(_iter_json_objects(output))
    if not candidates:
        return output

    for candidate in candidates:
        try:
            _ = Coords.model_validate_json(json_repair.repair_json(candidate))
        except (ValidationError, ValueError):
            continue
        return candidate

    return candidates[-1]


def parse_coordinates(output: str) -> Coords:
    """Parse coordinates after selecting the best candidate from noisy output."""
    candidate = select_coordinate_candidate(output)
    return Coords.model_validate_json(json_repair.repair_json(candidate))
