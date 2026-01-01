from dataclasses import dataclass, field
from typing import Any, Literal, override

import numpy as np
import weave
from numpy.typing import NDArray
from PIL import Image
from pydantic import PrivateAttr
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim as cosine_similarity
from weave.trace.op import Op

from gptnt.dataset.defuser_vqa.constants import KEYPAD_SYMBOL_DESCRIPTIONS, TaskType

type PredictionOutput = dict[Literal["output"], str]

trick_question_categories = ["hallucination_type=type_a", "hallucination_type=type_b"]
"""Any trick categories that should be skipped during scoring.

typea = need more information typeb = something doesnt add up
"""


class GroundingScorer:
    """Scorer for grounding tasks."""

    def set_of_marks_accuracy(self, ground_truth: str, prediction: str) -> bool:
        """Calculate accuracy for SOM tasks."""
        return str(ground_truth).strip().lower() == str(prediction).strip().lower()

    def coordinate_accuracy(self, ground_truth: Image.Image, prediction: tuple[int, int]) -> bool:
        """Calculate accuracy for coordinate prediction tasks.

        The prediction is considered correct if it is within the threshold distance from the ground
        truth.
        """
        gt_mask = np.array(ground_truth)
        if not self._prediction_is_valid(prediction, gt_mask):
            return False  # Out of bounds
        predicted_region_id = gt_mask[prediction[1], prediction[0]]
        return bool(predicted_region_id)

    def coordinate_distance(self, ground_truth: Image.Image, prediction: tuple[int, int]) -> float:
        """Calculate distance for coordinate prediction tasks.

        The distance is calculated between the predicted coordinates and the closest pixel of the
        ground truth region.
        """
        width, height = ground_truth.width, ground_truth.height
        # Check if predicted coordinates are out of bounds
        max_distance = np.sqrt(height**2 + width**2)
        gt_mask = np.array(ground_truth)
        if not self._prediction_is_valid(prediction, gt_mask):
            return max_distance

        # Find all pixels belonging to the ground truth region
        ys, xs = gt_mask.nonzero()
        dx = (xs - prediction[0]).astype(np.float64)
        dy = (ys - prediction[1]).astype(np.float64)
        distances = np.sqrt(dx**2 + dy**2)
        return float(np.min(distances))

    def _get_grounding_region_id(self, ground_truth: str | int) -> int:
        """Get the region ID for grounding tasks."""
        if isinstance(ground_truth, str):
            if not ground_truth.isdigit():
                raise ValueError(
                    "Ground truth must be an integer or string representing an integer."
                )
            ground_truth = int(ground_truth)
        return ground_truth

    def _prediction_is_valid(
        self, prediction: tuple[int, int], gt_mask: NDArray[np.uint8]
    ) -> bool:
        """Check if the prediction is valid."""
        x_coord, y_coord = prediction
        if x_coord < 0 or y_coord < 0:
            return False  # Out of bounds
        return y_coord < gt_mask.shape[0] and x_coord < gt_mask.shape[1]


@dataclass(kw_only=True)
class CompareToGroundTruth:  # noqa: WPS338
    """Give a module, is the answer correct."""

    task_type: TaskType | None
    similarity_ratio_threshold: float = 1.5
    sentence_transformer: SentenceTransformer = field(init=False, repr=False)
    keypad_cache: dict[str, Any] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the SentenceTransformer model and keypad cache."""
        self.sentence_transformer = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        self.keypad_cache = self.precompute_keypad_embeddings()

    def __call__(
        self, output: PredictionOutput, ground_truth: str | list[str], *, module: str
    ) -> bool:
        """Compare the output to the ground truth."""
        if module == "keypad" and self.task_type == "vqa":
            ground_truth_symbol = (
                ground_truth[0] if isinstance(ground_truth, list) else ground_truth
            )
            is_correct = self.check_keypad_result(
                input_string=output["output"], correct_symbol=ground_truth_symbol
            )
            return is_correct

        model_output = output["output"].lower().strip()
        if module == "morse":
            model_output = model_output.replace("mhz", "").strip()
        cleaned_ground_truth = (
            ground_truth.lower().strip()
            if isinstance(ground_truth, str)
            else [answer.lower().strip() for answer in ground_truth]
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
            ]
            embeddings_cache[symbol] = np.mean(embeddings, axis=0)
        return embeddings_cache


class ModuleScorer(weave.Scorer):
    """Module Scorer."""

    skip_trick_questions: bool = True
    _compute_ground_truth: CompareToGroundTruth = PrivateAttr()

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
        is_correct = self._compute_ground_truth(output, ground_truth, module=module_name)
        return {"total": is_correct, module_name: is_correct}


class CategoryPrefixScorer(weave.Scorer):
    """Scorer for a given category prefix."""

    prefix: str
    skip_trick_questions: bool = True

    _compute_ground_truth: CompareToGroundTruth = PrivateAttr()

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
        is_correct = self._compute_ground_truth(output, ground_truth, module=module_name)
        return {category_name: {"total": is_correct, "module": {module_name: is_correct}}}


def load_all_scorers(task_type: TaskType | None) -> list[Op[..., Any] | weave.Scorer]:
    """Load all scorers."""
    compare_to_ground_truth_fn = CompareToGroundTruth(task_type=task_type)
    score_modules = ModuleScorer(name="module")
    score_modules._compute_ground_truth = compare_to_ground_truth_fn  # noqa: SLF001
    score_detection = CategoryPrefixScorer(name="detect", prefix="detect")
    score_detection._compute_ground_truth = compare_to_ground_truth_fn  # noqa: SLF001
    score_question_type = CategoryPrefixScorer(name="question_type", prefix="question_type")
    score_question_type._compute_ground_truth = compare_to_ground_truth_fn  # noqa: SLF001
    score_hallucination = CategoryPrefixScorer(
        name="hallucination_type", prefix="hallucination_type", skip_trick_questions=False
    )
    score_hallucination._compute_ground_truth = compare_to_ground_truth_fn  # noqa: SLF001

    return [score_modules, score_detection, score_hallucination, score_question_type]
