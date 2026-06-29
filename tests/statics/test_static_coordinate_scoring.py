"""Tests for evaluation scorers."""

from functools import partial
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray
from pytest_cases import parametrize_with_cases

from gptnt.statics.evaluation.constants import (
    GROUNDING_HALLUCINATION_TYPE_A_RESPONSE,
    GROUNDING_HALLUCINATION_TYPE_B_RESPONSE,
)
from gptnt.statics.evaluation.postprocess import convert_normalised_to_absolute
from gptnt.statics.evaluation.scorers import CoordinateValidator, CoordinateValidatorResult


def create_binary_mask(
    width: int, height: int, regions: list[tuple[int, int, int, int]] | None = None
) -> NDArray[np.uint8]:
    """Create a binary mask with specified dimensions.

    Args:
        width: Width of the mask
        height: Height of the mask
        regions: List of (x_start, y_start, x_end, y_end) tuples defining non-zero regions.
                 If None, creates an all-zero mask.

    Returns:
        Binary mask as uint8 numpy array with shape (height, width)
    """
    mask = np.zeros((height, width), dtype=np.uint8)
    if regions:
        for x_start, y_start, x_end, y_end in regions:
            mask[y_start:y_end, x_start:x_end] = 1
    return mask


def test_create_binary_mask_all_zeros() -> None:
    """Test create_binary_mask with no regions."""
    mask = create_binary_mask(50, 30)
    assert mask.shape == (30, 50)
    assert mask.dtype == np.uint8
    assert np.all(mask == 0)


def test_create_binary_mask_single_region() -> None:
    """Test create_binary_mask with one region."""
    mask = create_binary_mask(100, 100, regions=[(10, 20, 30, 40)])
    assert mask.shape == (100, 100)
    assert mask[25, 15] == 1  # Inside region (y=25, x=15)
    assert mask[10, 10] == 0  # Outside region
    assert mask[50, 50] == 0  # Outside region


def test_create_binary_mask_multiple_regions() -> None:
    """Test create_binary_mask with multiple regions."""
    mask = create_binary_mask(100, 100, regions=[(10, 10, 20, 20), (50, 50, 60, 60)])
    assert mask[15, 15] == 1  # First region
    assert mask[55, 55] == 1  # Second region
    assert mask[30, 30] == 0  # Between regions


class CoordinateValidatorCase(NamedTuple):
    """Test case for CoordinateValidator."""

    output: dict[str, str]
    ground_truth: NDArray[np.uint8] | str
    expected_result: CoordinateValidatorResult
    module: str
    description: str


class CoordinateValidatorCases:
    """Test cases for CoordinateValidator scorer."""

    # Shared test dimensions
    width = 100
    height = 100

    def case_valid_json_in_bounds(self) -> CoordinateValidatorCase:
        """Valid JSON coordinate within bounds."""
        mask = create_binary_mask(self.width, self.height, regions=[(10, 10, 20, 20)])
        return CoordinateValidatorCase(
            output={"output": '{"x": 15, "y": 15}'},
            ground_truth=mask,
            expected_result="valid_format",
            module="test_module",
            description="Valid JSON with coordinates in bounds",
        )

    def case_valid_json_at_boundary(self) -> CoordinateValidatorCase:
        """Valid JSON coordinate at the boundary."""
        mask = create_binary_mask(self.width, self.height)
        return CoordinateValidatorCase(
            output={"output": f'{{"x": {self.width}, "y": {self.height}}}'},
            ground_truth=mask,
            expected_result="valid_format",
            module="test_module",
            description="Valid JSON with coordinates at boundary",
        )

    def case_valid_json_with_markdown_wrapper(self) -> CoordinateValidatorCase:
        """Valid JSON wrapped in markdown code blocks."""
        mask = create_binary_mask(self.width, self.height)
        return CoordinateValidatorCase(
            output={"output": '```json\n{"x": 50, "y": 50}\n```'},
            ground_truth=mask,
            expected_result="valid_format",
            module="test_module",
            description="Valid JSON wrapped in markdown blocks",
        )

    def case_valid_json_with_whitespace(self) -> CoordinateValidatorCase:
        """Valid JSON with extra whitespace."""
        mask = create_binary_mask(self.width, self.height)
        return CoordinateValidatorCase(
            output={"output": '  {"x": 25, "y": 75}  \n'},
            ground_truth=mask,
            expected_result="valid_format",
            module="test_module",
            description="Valid JSON with whitespace",
        )

    def case_out_of_bounds_x(self) -> CoordinateValidatorCase:
        """Coordinate with x out of bounds."""
        mask = create_binary_mask(self.width, self.height)
        return CoordinateValidatorCase(
            output={"output": f'{{"x": {self.width + 1}, "y": 50}}'},
            ground_truth=mask,
            expected_result="out_of_bounds",
            module="test_module",
            description="X coordinate exceeds bounds",
        )

    def case_out_of_bounds_y(self) -> CoordinateValidatorCase:
        """Coordinate with y out of bounds."""
        mask = create_binary_mask(self.width, self.height)
        return CoordinateValidatorCase(
            output={"output": f'{{"x": 50, "y": {self.height + 1}}}'},
            ground_truth=mask,
            expected_result="out_of_bounds",
            module="test_module",
            description="Y coordinate exceeds bounds",
        )

    def case_out_of_bounds_negative(self) -> CoordinateValidatorCase:
        """Negative coordinates."""
        mask = create_binary_mask(self.width, self.height)
        return CoordinateValidatorCase(
            output={"output": '{"x": -5, "y": 50}'},
            ground_truth=mask,
            expected_result="out_of_bounds",
            module="test_module",
            description="Negative coordinate",
        )

    def case_invalid_json_missing_field(self) -> CoordinateValidatorCase:
        """Invalid JSON missing required field."""
        mask = create_binary_mask(self.width, self.height)
        return CoordinateValidatorCase(
            output={"output": '{"x": 50}'},
            ground_truth=mask,
            expected_result="invalid_format",
            module="test_module",
            description="JSON missing y field",
        )

    def case_invalid_json_wrong_type(self) -> CoordinateValidatorCase:
        """Invalid JSON with wrong data type."""
        mask = create_binary_mask(self.width, self.height)
        return CoordinateValidatorCase(
            output={"output": '{"x": "fifty", "y": 50}'},
            ground_truth=mask,
            expected_result="invalid_format",
            module="test_module",
            description="JSON with string instead of int",
        )

    def case_invalid_json_malformed(self) -> CoordinateValidatorCase:
        """Malformed JSON that cannot be repaired."""
        mask = create_binary_mask(self.width, self.height)
        return CoordinateValidatorCase(
            output={"output": "not json at all"},
            ground_truth=mask,
            expected_result="invalid_format",
            module="test_module",
            description="Malformed JSON",
        )

    def case_invalid_json_array(self) -> CoordinateValidatorCase:
        """JSON array instead of object."""
        mask = create_binary_mask(self.width, self.height)
        return CoordinateValidatorCase(
            output={"output": "[50, 50]"},
            ground_truth=mask,
            expected_result="invalid_format",
            module="test_module",
            description="Array instead of object",
        )

    def case_hallucination_type_a(self) -> CoordinateValidatorCase:
        """Hallucination type A response with string ground truth."""
        return CoordinateValidatorCase(
            output={"output": GROUNDING_HALLUCINATION_TYPE_A_RESPONSE},
            ground_truth=GROUNDING_HALLUCINATION_TYPE_A_RESPONSE,
            expected_result="valid_format",
            module="test_module",
            description="Hallucination type A should be valid",
        )

    def case_hallucination_type_b(self) -> CoordinateValidatorCase:
        """Hallucination type B response with string ground truth."""
        return CoordinateValidatorCase(
            output={"output": GROUNDING_HALLUCINATION_TYPE_B_RESPONSE},
            ground_truth=GROUNDING_HALLUCINATION_TYPE_B_RESPONSE,
            expected_result="valid_format",
            module="test_module",
            description="Hallucination type B should be valid",
        )

    def case_hallucination_wrong_response(self) -> CoordinateValidatorCase:
        """Wrong response when hallucination expected."""
        return CoordinateValidatorCase(
            output={"output": "some other text"},
            ground_truth=GROUNDING_HALLUCINATION_TYPE_A_RESPONSE,
            expected_result="invalid_format",
            module="test_module",
            description="Wrong hallucination response should be invalid",
        )

    def case_repairable_json(self) -> CoordinateValidatorCase:
        """JSON that can be repaired (missing quotes, trailing comma)."""
        mask = create_binary_mask(self.width, self.height)
        return CoordinateValidatorCase(
            output={"output": "{x: 30, y: 40,}"},
            ground_truth=mask,
            expected_result="valid_format",
            module="test_module",
            description="Repairable JSON should be valid",
        )


class CoordinateValidatorNormalisedCases:
    """Test cases for CoordinateValidator with normalised coordinates."""

    # Image dimensions for normalised coordinates
    image_width = 100
    image_height = 100
    normalised_upper_bound = 1000

    def case_normalised_valid(self) -> CoordinateValidatorCase:
        """Valid normalised coordinate."""
        mask = create_binary_mask(self.image_width, self.image_height)
        # Normalised (500, 500) -> Absolute (50, 50)
        return CoordinateValidatorCase(
            output={"output": '{"x": 500, "y": 500}'},
            ground_truth=mask,
            expected_result="valid_format",
            module="test_module",
            description="Valid normalised coordinate",
        )

    def case_normalised_at_max(self) -> CoordinateValidatorCase:
        """Normalised coordinate at maximum bound."""
        mask = create_binary_mask(self.image_width, self.image_height)
        # Normalised (1000, 1000) -> Absolute (100, 100)
        return CoordinateValidatorCase(
            output={
                "output": f'{{"x": {self.normalised_upper_bound}, "y": {self.normalised_upper_bound}}}'
            },
            ground_truth=mask,
            expected_result="valid_format",
            module="test_module",
            description="Normalised coordinate at max bound",
        )

    def case_normalised_zero(self) -> CoordinateValidatorCase:
        """Normalised coordinate at zero."""
        mask = create_binary_mask(self.image_width, self.image_height)
        return CoordinateValidatorCase(
            output={"output": '{"x": 0, "y": 0}'},
            ground_truth=mask,
            expected_result="valid_format",
            module="test_module",
            description="Normalised coordinate at zero",
        )

    def case_normalised_out_of_bounds(self) -> CoordinateValidatorCase:
        """Normalised coordinate that exceeds bounds."""
        mask = create_binary_mask(self.image_width, self.image_height)
        # Normalised (1500, 500) -> Absolute (150, 50) - out of bounds
        return CoordinateValidatorCase(
            output={"output": '{"x": 1500, "y": 500}'},
            ground_truth=mask,
            expected_result="out_of_bounds",
            module="test_module",
            description="Normalised coordinate exceeds bounds",
        )


@parametrize_with_cases("test_case", cases=CoordinateValidatorCases)
def test_coordinate_validator_default(test_case: CoordinateValidatorCase) -> None:
    """Test CoordinateValidator with default postprocess function."""
    validator = CoordinateValidator(task_type=None)
    result = validator(test_case.output, test_case.ground_truth, module=test_case.module)
    assert result == test_case.expected_result, test_case.description


@parametrize_with_cases("test_case", cases=CoordinateValidatorNormalisedCases)
def test_coordinate_validator_normalised(test_case: CoordinateValidatorCase) -> None:
    """Test CoordinateValidator with normalised to absolute postprocess function."""
    postprocess_func = partial(
        convert_normalised_to_absolute,
        image_width=CoordinateValidatorNormalisedCases.image_width,
        image_height=CoordinateValidatorNormalisedCases.image_height,
    )
    validator = CoordinateValidator(task_type=None, postprocess_output_func=postprocess_func)
    result = validator(test_case.output, test_case.ground_truth, module=test_case.module)
    assert result == test_case.expected_result, test_case.description
