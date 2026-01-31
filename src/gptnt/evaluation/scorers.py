import abc
from dataclasses import dataclass, field
from typing import Any, Literal, override

import json_repair
import numpy as np
import weave
from numpy.typing import NDArray
from pydantic import BaseModel, PrivateAttr
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim as cosine_similarity
from weave.trace.op import Op

from gptnt.dataset.defuser_vqa.constants import KEYPAD_SYMBOL_DESCRIPTIONS, TaskType
from gptnt.evaluation.postprocess import PostProcessModelOutputsFunc, default

type PredictionOutput = dict[Literal["output"], str]

type GroundTruthType = str | list[str] | NDArray[np.uint8]
"""Type for ground truth values.

Can be a string, list of strings, or a numpy array for binary masks.
"""


trick_question_categories = ["hallucination_type=type_a", "hallucination_type=type_b"]
"""Any trick categories that should be skipped during scoring.

typea = need more information typeb = something doesnt add up
"""


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

    postprocess_output_func: PostProcessModelOutputsFunc = field(default=default, repr=False)

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
        if module == "keypad" and self.task_type == "vqa":
            ground_truth_symbol = (
                ground_truth[0] if isinstance(ground_truth, list) else ground_truth
            )
            is_correct = self.check_keypad_result(
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

    def check_keypad_result(self, input_string: str, correct_symbol: str) -> bool:
        """Checks if the input aligns with the correct symbol based on similarity metrics."""
        input_embedding = self.sentence_transformer.encode(
            [input_string], normalize_embeddings=True
        )[0]

        cluster_similarities = {}
        for symbol, mean_embedding in self.keypad_cache.items():
            cluster_similarities[symbol] = cosine_similarity(
                mean_embedding, input_embedding
            ).item()

        sorted_clusters = sorted(
            cluster_similarities.items(), key=lambda pair: pair[1], reverse=True
        )
        most_similar_symbol, most_similar_score = sorted_clusters[0]
        _, _second_most_similar_score = sorted_clusters[1]

        if most_similar_symbol != correct_symbol:
            return False

        # Remove the correct symbol from the sorted clusters to calculate similarity ratio
        _ = cluster_similarities.pop(correct_symbol)
        return self.check_keypad_metrics(most_similar_score, cluster_similarities)

    def check_keypad_metrics(
        self, most_similar_score: float, non_correct_clusters: dict[str, float]
    ) -> bool:
        """Calculate contrast ratio and separation score."""
        similarity_ratio = most_similar_score / np.mean(list(non_correct_clusters.values())).item()

        return similarity_ratio > self.similarity_ratio_threshold

    def precompute_keypad_embeddings(self) -> dict[str, np.ndarray[Any, Any]]:
        """Precompute and cache embeddings for KEYPAD_SYMBOL_DESCRIPTIONS."""
        embeddings_cache = {}
        for symbol, descriptions in KEYPAD_SYMBOL_DESCRIPTIONS.items():
            embeddings = [
                self.sentence_transformer.encode([description], normalize_embeddings=True)[0]
                for description in descriptions
                if self._is_valid_description(description)
            ]
            embeddings_cache[symbol] = np.mean(embeddings, axis=0)
        return embeddings_cache

    def _is_valid_description(self, description: str) -> bool:
        """Filter out descriptions based on tokenization consistency."""
        # Make sure encoding and decoding are consistent (no <unk> tokens)
        token_ids = self.sentence_transformer.tokenizer.encode(
            description, add_special_tokens=False
        )
        decoded_description = self.sentence_transformer.tokenizer.decode(token_ids)
        return description == decoded_description


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
        parsed_coords = Coords.model_validate_json(cleaned_output)

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
class CoordinateDistanceComparer(BaseComparer[NDArray[np.uint8] | str, float]):
    """Scorer to check distance from correct coordinate.

    Note: Array indexing is (y, x) for rows and columns.
    The distance is normalized to be in [0.0, 1.0].
    """

    _min_distance: float = 0.0  # noqa: WPS358
    _max_distance: float = 1.0

    @override
    def __call__(
        self, output: PredictionOutput, ground_truth: NDArray[np.uint8] | str, *, module: str
    ) -> float:
        if isinstance(ground_truth, str):
            return self.score_with_string_ground_truth(output, ground_truth)
        return self.score_with_array_ground_truth(output, ground_truth)

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
        parsed_coords = Coords.model_validate_json(cleaned_output)

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

        dx = xs - coords.x
        dy = ys - coords.y
        distances = np.sqrt(dx**2 + dy**2)
        distance = float(np.min(distances))
        # Normalize distance
        max_possible_distance = np.sqrt(ground_truth.shape[0] ** 2 + ground_truth.shape[1] ** 2)
        return distance / max_possible_distance


class ModuleScorer(weave.Scorer):
    """Module Scorer."""

    skip_trick_questions: bool = True
    _comparer: BaseComparer[Any, Any] = PrivateAttr()

    @weave.op
    @override
    def score(  # pyright: ignore[reportIncompatibleVariableOverride]
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

        # Find the module
        module_tag = [category for category in categories if category.startswith("module=")]
        if not module_tag:
            return None

        module_name = module_tag[0].split("=", 1)[1]
        score = self._comparer(output, ground_truth, module=module_name)
        return {"total": score, module_name: score}


class CategoryPrefixScorer(weave.Scorer):
    """Scorer for a given category prefix."""

    prefix: str
    skip_trick_questions: bool = True

    _comparer: BaseComparer[Any, Any] = PrivateAttr()

    @weave.op
    @override
    def score(  # pyright: ignore[reportIncompatibleVariableOverride]
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

        # Find the module
        module_tag = [category for category in categories if category.startswith("module=")]
        if not module_tag:
            return None

        # Find the prefix
        prefix_tag = [
            category for category in categories if category.startswith(f"{self.prefix}=")
        ]
        if not prefix_tag:
            return None

        module_name = module_tag[0].split("=", 1)[1]
        category_name = prefix_tag[0].split("=", 1)[1]
        score = self._comparer(output, ground_truth, module=module_name)
        return {category_name: {"total": score, "module": {module_name: score}}}


def create_scorers(comparer: BaseComparer[Any, Any]) -> list[Op[..., Any] | weave.Scorer]:
    """Create the scorers for the task."""
    # compare_to_ground_truth_fn = CompareToGroundTruth(task_type=task_type)
    score_modules = ModuleScorer(name="module")
    score_modules._comparer = comparer  # noqa: SLF001
    score_detection = CategoryPrefixScorer(name="detect", prefix="detect")
    score_detection._comparer = comparer  # noqa: SLF001
    score_question_type = CategoryPrefixScorer(name="question_type", prefix="question_type")
    score_question_type._comparer = comparer  # noqa: SLF001
    score_hallucination = CategoryPrefixScorer(
        name="hallucination_type", prefix="hallucination_type", skip_trick_questions=False
    )
    score_hallucination._comparer = comparer  # noqa: SLF001
    return [score_modules, score_detection, score_hallucination, score_question_type]
