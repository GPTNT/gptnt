from dataclasses import dataclass, field
from typing import Any, Literal, override

import numpy as np
import weave
from pydantic import PrivateAttr
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim as cosine_similarity
from weave.trace.op import Op

from gptnt.dataset.generate_instructions import KEYPAD_SYMBOL_DESCRIPTIONS, TaskType

type PredictionOutput = dict[Literal["output"], str]

trick_question_categories = ["hallucination_type=type_a", "hallucination_type=type_b"]


@dataclass(kw_only=True)
class CompareToGroundTruth:  # noqa: WPS338
    """Give a module, is the answer correct."""

    task_type: TaskType
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
        if isinstance(ground_truth, list):
            return output["output"] in ground_truth
        return output["output"] == ground_truth

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
        _, second_most_similar_score = sorted_clusters[1]

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
        self, output: PredictionOutput, ground_truth: str | list[str], categories: list[str]
    ) -> dict[str, Any] | None:
        """Score the prediction based on the module."""
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


class PrefixScorer(weave.Scorer):
    """Scorer for a given category prefix."""

    prefix: str
    skip_trick_questions: bool = True

    _compute_ground_truth: CompareToGroundTruth = PrivateAttr()

    @weave.op
    @override
    def score(  # pyright: ignore[reportIncompatibleVariableOverride]
        self, output: PredictionOutput, ground_truth: str | list[str], categories: list[str]
    ) -> dict[str, Any] | None:
        """Score the prediction based on the prefix."""
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


def load_all_scorers(task_type: TaskType) -> list[Op[..., Any] | weave.Scorer]:
    """Load all scorers."""
    compare_to_ground_truth_fn = CompareToGroundTruth(task_type=task_type)
    score_modules = ModuleScorer(name="module")
    score_modules._compute_ground_truth = compare_to_ground_truth_fn  # noqa: SLF001
    score_detection = PrefixScorer(name="detect", prefix="detect")
    score_detection._compute_ground_truth = compare_to_ground_truth_fn  # noqa: SLF001
    score_question_type = PrefixScorer(name="question_type", prefix="question_type")
    score_question_type._compute_ground_truth = compare_to_ground_truth_fn  # noqa: SLF001
    score_hallucination = PrefixScorer(
        name="hallucination_type", prefix="hallucination_type", skip_trick_questions=False
    )
    score_hallucination._compute_ground_truth = compare_to_ground_truth_fn  # noqa: SLF001

    return [score_modules, score_detection, score_hallucination, score_question_type]
