from __future__ import annotations

import abc
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal, override

import json_repair
import numpy as np
from more_itertools import collapse
from numpy.typing import NDArray
from pydantic import BaseModel, ValidationError
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim as cosine_similarity

from gptnt.statics.evaluation.postprocess import PostProcessModelOutputsFunc, default_postprocess
from gptnt.statics.generation.defuser_vqa.constants import (
    GROUNDING_HALLUCINATION_TYPE_A_RESPONSE,
    GROUNDING_HALLUCINATION_TYPE_B_RESPONSE,
    KEYPAD_SYMBOL_DESCRIPTIONS,
    TaskType,
)

type PredictionOutput = dict[Literal["output"], str]

type GroundTruthType = str | list[str] | NDArray[np.uint8]
"""Type for ground truth values.

Can be a string, list of strings, or a numpy array for binary masks.
"""


trick_question_categories = ["hallucination_type=type_a", "hallucination_type=type_b"]
"""Any trick categories that should be skipped during scoring.

typea = need more information typeb = something doesnt add up
"""


type CoordinateValidatorResult = Literal["valid_format", "invalid_format", "out_of_bounds"]


def check_for_bad_symbols(
    symbols: list[str], *, sentence_transformer: SentenceTransformer
) -> list[str]:
    """Check for any symbols that do not tokenize/decode properly."""
    bad_symbols = []
    for symbol in symbols:
        tokens = sentence_transformer.tokenizer.encode(symbol, add_special_tokens=False)
        decoded = sentence_transformer.tokenizer.decode(tokens)
        if decoded.strip() != symbol.strip():
            bad_symbols.append(symbol)
    return bad_symbols


class Coords(BaseModel):
    """Coordinate dictionary.

    Just to keep things explicit.
    """

    x: int  # noqa: WPS111
    y: int  # noqa: WPS111

    def is_in_bounds(self, width: int, height: int) -> bool:
        """Check if the coordinates are within the bounds."""
        return 0 <= self.x <= width and 0 <= self.y <= height


@dataclass(kw_only=True)
class BaseComparer[GroundTruthT, ReturnT](abc.ABC):
    """Base Scorer class.

    Just to get the protocols in place.
    """

    task_type: TaskType | None

    postprocess_output_func: PostProcessModelOutputsFunc = field(
        default=default_postprocess, repr=False
    )

    @abc.abstractmethod
    def __call__(
        self, output: PredictionOutput, ground_truth: GroundTruthT, *, module: str
    ) -> ReturnT:
        """Compare the output to the ground truth."""
        raise NotImplementedError


@dataclass(kw_only=True)
class StringBasedComparer(BaseComparer[str | list[str], bool]):  # noqa: WPS338
    """Perform string-based comparisons to ground truth."""

    similarity_ratio_threshold: float = 1.5
    sentence_transformer: SentenceTransformer = field(init=False, repr=False)
    keypad_cache: dict[str, Any] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the SentenceTransformer model and keypad cache."""
        self.sentence_transformer = SentenceTransformer(
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", device="cpu"
        )
        self.keypad_cache = self.precompute_keypad_embeddings()

    @override
    def __call__(
        self, output: PredictionOutput, ground_truth: str | list[str], *, module: str
    ) -> bool:
        if module == "keypad" and self.task_type == "oe":
            ground_truth_symbol = (
                ground_truth[0] if isinstance(ground_truth, list) else ground_truth
            )
            is_correct = self.check_keypad_with_exact_match(
                input_string=output["output"], correct_symbol=ground_truth_symbol
            )
            if not is_correct:
                is_correct = self.check_keypad_with_embeddings(
                    input_string=output["output"], correct_symbol=ground_truth_symbol
                )
            return is_correct

        model_output = self.postprocess_output_func(output["output"])
        if module == "morse":
            model_output = model_output.replace("mhz", "").strip()
        cleaned_ground_truth = (
            self.postprocess_output_func(ground_truth)
            if isinstance(ground_truth, str)
            else [self.postprocess_output_func(answer) for answer in ground_truth]
        )
        if isinstance(ground_truth, list):
            return model_output in cleaned_ground_truth
        return model_output == cleaned_ground_truth

    def check_keypad_with_exact_match(self, input_string: str, correct_symbol: str) -> bool:
        """Checks if the input matches the correct symbol or its descriptions exactly."""
        cleaned_input = self.postprocess_output_func(input_string).strip().lower()
        alternatives = {correct_symbol, *KEYPAD_SYMBOL_DESCRIPTIONS[correct_symbol]}
        alternatives = {symbol.strip().lower() for symbol in alternatives}
        return cleaned_input in alternatives

    def check_keypad_with_embeddings(self, input_string: str, correct_symbol: str) -> bool:
        """Checks if the input aligns with the correct symbol based on similarity metrics."""
        output_embedding = self.sentence_transformer.encode(
            [input_string], normalize_embeddings=True
        )
        output_embedding = np.ravel(output_embedding)

        # Get a list of all the alternatives to compare against
        symbols_to_compare_with = list(
            {correct_symbol, *KEYPAD_SYMBOL_DESCRIPTIONS[correct_symbol]}
        )
        embeddings_to_compare = [
            self.keypad_cache[symbol]
            for symbol in symbols_to_compare_with
            if symbol in self.keypad_cache
        ]

        for embedding in embeddings_to_compare:
            similarity = cosine_similarity(output_embedding, embedding).item()
            if similarity >= self.similarity_ratio_threshold:
                return True
        return False

    def precompute_keypad_embeddings(self) -> dict[str, np.ndarray[Any, Any]]:
        """Precompute and cache embeddings for KEYPAD_SYMBOL_DESCRIPTIONS."""
        all_symbols: list[str] = list(collapse(KEYPAD_SYMBOL_DESCRIPTIONS.items()))
        bad_symbols = check_for_bad_symbols(
            all_symbols, sentence_transformer=self.sentence_transformer
        )
        all_non_bad_symbols = [symbol for symbol in all_symbols if symbol not in bad_symbols]

        all_embeddings = self.sentence_transformer.encode(
            all_non_bad_symbols, normalize_embeddings=True
        )
        symbol_to_embedding = dict(
            zip(
                all_non_bad_symbols,
                map(np.squeeze, np.split(all_embeddings, len(all_non_bad_symbols))),
                strict=True,
            )
        )

        return symbol_to_embedding


@dataclass(kw_only=True)
class CoordinateValidator(BaseComparer[NDArray[np.uint8], CoordinateValidatorResult]):
    """Validate predicted coordinates."""

    @override
    def __call__(
        self, output: PredictionOutput, ground_truth: NDArray[np.uint8] | str, *, module: str
    ) -> CoordinateValidatorResult:
        cleaned_output = self.postprocess_output_func(output["output"])
        if isinstance(ground_truth, str):
            return self.validate_string_ground_truth(cleaned_output)
        return self.validate_array_ground_truth(cleaned_output, ground_truth)

    def validate_string_ground_truth(self, cleaned_output: str) -> CoordinateValidatorResult:
        """Validate the output against string ground truth."""
        if cleaned_output in {
            GROUNDING_HALLUCINATION_TYPE_A_RESPONSE.lower(),
            GROUNDING_HALLUCINATION_TYPE_B_RESPONSE.lower(),
        }:
            return "valid_format"
        return "invalid_format"

    def validate_array_ground_truth(
        self, cleaned_output: str, ground_truth: NDArray[np.uint8]
    ) -> CoordinateValidatorResult:
        """Validate the output against array ground truth."""
        try:
            parsed_coords = Coords.model_validate_json(json_repair.repair_json(cleaned_output))
        except ValidationError:
            return "invalid_format"

        if not parsed_coords.is_in_bounds(ground_truth.shape[1], ground_truth.shape[0]):
            return "out_of_bounds"

        return "valid_format"


@dataclass(kw_only=True)
class CoordinateInRegionComparer(BaseComparer[NDArray[np.uint8] | str, bool]):
    """Comparer for coordinate in region tasks.

    Note: Array indexing is (y, x) for rows and columns.
    """

    @override
    def __call__(
        self, output: PredictionOutput, ground_truth: NDArray[np.uint8] | str, *, module: str
    ) -> bool:
        if isinstance(ground_truth, str):
            return self.score_with_string_ground_truth(output, ground_truth)
        return self.score_with_array_ground_truth(output, ground_truth)

    def score_with_string_ground_truth(self, output: PredictionOutput, ground_truth: str) -> bool:
        """Score when ground truth is a string (hallucination question)."""
        cleaned_output = self.postprocess_output_func(output["output"])
        cleaned_ground_truth = self.postprocess_output_func(ground_truth)
        return cleaned_output == cleaned_ground_truth

    def score_with_array_ground_truth(
        self, output: PredictionOutput, ground_truth: NDArray[np.uint8]
    ) -> bool:
        """Score when ground truth is a binary mask array."""
        cleaned_output = json_repair.repair_json(self.postprocess_output_func(output["output"]))

        try:
            parsed_coords = Coords.model_validate_json(cleaned_output)
        except ValidationError:
            return False

        if not parsed_coords.is_in_bounds(ground_truth.shape[1], ground_truth.shape[0]):
            # Out of bounds
            return False

        # We need to bound to avoid indexing errors incase the models do 0-based vs 1-based coords,
        # which are negligible differences in practice
        bounded_x = min(max(parsed_coords.x, 0), ground_truth.shape[1] - 1)
        bounded_y = min(max(parsed_coords.y, 0), ground_truth.shape[0] - 1)

        # Non-zero indicates correct region
        return bool(ground_truth[bounded_y, bounded_x])


@dataclass(kw_only=True)
class CoordinateDistanceComparer(BaseComparer[NDArray[np.uint8] | str, float], abc.ABC):
    """Scorer to check distance from correct coordinate.

    Note: Array indexing is (y, x) for rows and columns.
    """

    image_height: int
    image_width: int
    _normalize_distance: bool
    _min_distance: float = 0.0  # noqa: WPS358

    @override
    def __call__(
        self, output: PredictionOutput, ground_truth: NDArray[np.uint8] | str, *, module: str
    ) -> float:
        if isinstance(ground_truth, str):
            return self.score_with_string_ground_truth(output, ground_truth)
        return self.score_with_array_ground_truth(output, ground_truth)

    def __post_init__(self) -> None:
        """Compute the max distance based on image dimensions."""
        self._normalization_factor = self._compute_max_image_distance(
            self.image_height, self.image_width
        )
        self._max_distance = 1.0 if self._normalize_distance else self._normalization_factor

    def score_with_string_ground_truth(self, output: PredictionOutput, ground_truth: str) -> float:
        """Score when ground truth is a string (hallucination question)."""
        cleaned_output = self.postprocess_output_func(output["output"])
        cleaned_ground_truth = self.postprocess_output_func(ground_truth)
        if cleaned_output == cleaned_ground_truth:
            return self._min_distance
        return self._max_distance

    def score_with_array_ground_truth(
        self, output: PredictionOutput, ground_truth: NDArray[np.uint8]
    ) -> float:
        """Score when ground truth is a binary mask array."""
        cleaned_output = json_repair.repair_json(self.postprocess_output_func(output["output"]))

        try:
            parsed_coords = Coords.model_validate_json(cleaned_output)
        except ValidationError:
            return self._max_distance

        if not parsed_coords.is_in_bounds(ground_truth.shape[1], ground_truth.shape[0]):
            # Out of bounds
            return self._max_distance

        return self._get_closest_distance_to_region(ground_truth, parsed_coords)

    def _get_closest_distance_to_region(
        self, ground_truth: NDArray[np.uint8], coords: Coords
    ) -> float:
        """Get the closest distance from the predicted coordinates to the ground truth region."""
        ys, xs = ground_truth.nonzero()

        if len(ys) == 0 or len(xs) == 0:
            # No valid region in ground truth, return max distance
            return self._max_distance

        distances = self._compute_distances(ground_truth, coords)
        distance = float(np.min(distances))
        if self._normalize_distance:
            # Normalize distance
            return distance / self._normalization_factor
        return distance

    @abc.abstractmethod
    def _compute_max_image_distance(self, image_height: int, image_width: int) -> float:
        """Calculate the maximum possible distance based on image dimensions."""
        raise NotImplementedError

    @abc.abstractmethod
    def _compute_distances(
        self, ground_truth: NDArray[np.uint8], coords: Coords
    ) -> NDArray[np.float64]:
        """Get the distances from the predicted to the ground truth coordinates."""
        raise NotImplementedError


@dataclass(kw_only=True)
class CoordinateEuclideanDistanceComparer(CoordinateDistanceComparer):
    """Scorer to check euclidean distance from correct coordinate.

    The distance is normalized to be in [0.0, 1.0].
    """

    _normalize_distance: bool = True

    @override
    def _compute_max_image_distance(self, image_height: int, image_width: int) -> float:
        """Calculate the maximum possible distance for normalization."""
        distance = np.sqrt(image_height**2 + image_width**2)
        return float(distance)

    @override
    def _compute_distances(
        self, ground_truth: NDArray[np.uint8], coords: Coords
    ) -> NDArray[np.float64]:
        """Get the distances from the predicted to the ground truth coordinates."""
        ys, xs = ground_truth.nonzero()
        dx = xs - coords.x
        dy = ys - coords.y
        distances = np.sqrt(dx**2 + dy**2)
        return distances


@dataclass(kw_only=True)
class CoordinateAbsoluteDistanceComparer(CoordinateDistanceComparer):
    """Scorer to check absolute distance from correct coordinate.

    The distance is NOT normalized.
    """

    _normalize_distance: bool = False

    @override
    def _compute_max_image_distance(self, image_height: int, image_width: int) -> float:
        """Calculate the maximum possible distance for normalization."""
        return float(image_height + image_width)

    @override
    def _compute_distances(
        self, ground_truth: NDArray[np.uint8], coords: Coords
    ) -> NDArray[np.float64]:
        """Get the distances from the predicted to the ground truth coordinates."""
        ys, xs = ground_truth.nonzero()
        dx = xs - coords.x
        dy = ys - coords.y
        distances = np.abs(dx) + np.abs(dy)
        return distances


@dataclass(kw_only=True)
class ModuleScorer:
    """Score a prediction, broken down per KTANE module."""

    name: str
    comparer: BaseComparer[Any, Any]
    skip_trick_questions: bool = True

    def score(
        self,
        output: PredictionOutput,
        ground_truth: str | list[str],
        categories: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Score the prediction based on the module."""
        if not categories:
            return None

        if self.skip_trick_questions and any(
            category in trick_question_categories for category in categories
        ):
            return None

        module_tag = [category for category in categories if category.startswith("module=")]
        if not module_tag:
            return None

        module_name = module_tag[0].split("=", 1)[1]
        score = self.comparer(output, ground_truth, module=module_name)
        return {"total": score, module_name: score}


@dataclass(kw_only=True)
class CategoryPrefixScorer:
    """Score a prediction, sliced by a category prefix (detect/question_type/...)."""

    name: str
    prefix: str
    comparer: BaseComparer[Any, Any]
    skip_trick_questions: bool = True

    def score(
        self,
        output: PredictionOutput,
        ground_truth: str | list[str],
        categories: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Score the prediction based on the category prefix."""
        if not categories:
            return None

        if self.skip_trick_questions and any(
            category in trick_question_categories for category in categories
        ):
            return None

        module_tag = [category for category in categories if category.startswith("module=")]
        if not module_tag:
            return None

        prefix_tag = [
            category for category in categories if category.startswith(f"{self.prefix}=")
        ]
        if not prefix_tag:
            return None

        module_name = module_tag[0].split("=", 1)[1]
        category_name = prefix_tag[0].split("=", 1)[1]
        score = self.comparer(output, ground_truth, module=module_name)
        return {category_name: {"total": score, "module": {module_name: score}}}


type Scorer = ModuleScorer | CategoryPrefixScorer


def create_scorers(comparer: BaseComparer[Any, Any]) -> list[Scorer]:
    """Create the standard slice scorers (module/detect/question_type/hallucination)."""
    return [
        ModuleScorer(name="module", comparer=comparer),
        CategoryPrefixScorer(name="detect", prefix="detect", comparer=comparer),
        CategoryPrefixScorer(
            name="hallucination_type",
            prefix="hallucination_type",
            comparer=comparer,
            skip_trick_questions=False,
        ),
        CategoryPrefixScorer(name="question_type", prefix="question_type", comparer=comparer),
    ]


type Instances = list[dict[str, Any]]
type Predictions = dict[int, dict[str, Any]]
type Metrics = dict[str, dict[str, float]]
type Sums = dict[str, float]
type Counts = dict[str, int]


def _accumulate(scored: dict[str, Any], sums: Sums, counts: Counts, *, prefix: str = "") -> None:
    """Flatten nested score dicts, accumulating numeric and categorical leaves by key path."""
    for name, leaf in scored.items():
        path = f"{prefix}{name}"
        if isinstance(leaf, dict):
            _accumulate(leaf, sums, counts, prefix=f"{path}.")
        elif isinstance(leaf, (int, float)):  # bool is a subclass of int
            sums[path] += float(leaf)
            counts[path] += 1
        elif isinstance(leaf, str):
            category = f"{path}={leaf}"
            sums[category] += 1
            counts[category] += 1


def score_predictions(
    scorers: list[Scorer], instances: Instances, predictions: Predictions
) -> Metrics:
    """Compute metrics locally (no Weave) for each scorer across all instances.

    `predictions` maps an instance index to its saved model-output dict. Numeric scores are
    averaged; string scores are reported as the fraction of instances in each category.
    """
    metrics: Metrics = {}
    for scorer in scorers:
        sums: Sums = defaultdict(float)
        counts: Counts = defaultdict(int)
        for instance in instances:
            prediction = predictions.get(instance["index"])
            if prediction is None:
                continue
            scored = scorer.score(
                {"output": prediction["output"]},
                instance["ground_truth"],
                instance.get("categories"),
            )
            if scored is not None:
                _accumulate(scored, sums, counts)
        metrics[scorer.name] = {name: sums[name] / counts[name] for name in sums}
    return metrics
