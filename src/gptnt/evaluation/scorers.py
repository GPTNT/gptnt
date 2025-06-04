from typing import Any, Literal, override

import numpy as np
import weave
from pydantic import PrivateAttr
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim as cosine_similarity
from weave.trace.op import Op

from gptnt.dataset.generate_instructions import KEYPAD_SYMBOL_DESCRIPTIONS, TaskType

type PredictionOutput = dict[Literal["output"], str]


def general_scorer(
    output: PredictionOutput,
    ground_truth: str | list[str],
    input_type: TaskType,
    categories: list[str],
) -> dict[str, bool | int | float] | None:
    """Score the prediction.

    Each key in the output dict will be a different grouping of metric for the weave.
    """
    if isinstance(ground_truth, list):
        is_correct = output["output"] in ground_truth
    else:
        is_correct = output["output"] == ground_truth

    # log whether it is correct or not
    score_output: dict[str, bool | int | float] = {"correct": is_correct}

    # log the input type
    score_output[str(input_type)] = is_correct

    # add each category with value is_correct
    for category in categories:
        score_output[category] = is_correct

    return score_output


def _create_module_scorer(*, module_name: str) -> Op[..., dict[str, bool | int | float] | None]:
    """Factory function to create a general-scorer for a specific module."""

    def scorer(  # noqa: WPS430
        output: PredictionOutput,
        ground_truth: str | list[str],
        input_type: TaskType,
        categories: list[str],
    ) -> dict[str, bool | int | float] | None:
        if f"module={module_name}" not in categories:
            return None
        return general_scorer(output, ground_truth, input_type, categories)

    scorer.__name__ = f"score_{module_name}"
    scorer.__doc__ = f"Score the {module_name} prediction."
    return weave.op(scorer)


def _create_prefix_scorer(
    *, prefix: str, scorer_name: str
) -> Op[..., dict[str, bool | int | float] | None]:
    """Factory function to create prefix-based scorers."""

    def scorer(  # noqa: WPS430
        output: PredictionOutput,
        ground_truth: str | list[str],
        input_type: TaskType,
        categories: list[str],
    ) -> dict[str, bool | int | float] | None:
        matching_categories = [cat for cat in categories if cat.startswith(f"{prefix}=")]
        if not matching_categories:
            return None
        return general_scorer(output, ground_truth, input_type, matching_categories)

    scorer.__name__ = f"score_{scorer_name}"
    scorer.__doc__ = f"Score the {scorer_name} prediction."
    return weave.op(scorer)


class KeypadScorer(weave.Scorer):
    """Scorer for the keypad module."""

    similarity_ratio_threshold: float = 1.5

    _sentence_transformer = PrivateAttr()
    _keypad_cache = PrivateAttr()

    def load_model(self) -> None:
        """Load the SentenceTransformer model."""
        self._sentence_transformer = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        self._keypad_cache = self.precompute_keypad_embeddings()

    def precompute_keypad_embeddings(self) -> dict[str, np.ndarray[Any, Any]]:
        """Precompute and cache embeddings for KEYPAD_SYMBOL_DESCRIPTIONS."""
        embeddings_cache = {}
        for symbol, descriptions in KEYPAD_SYMBOL_DESCRIPTIONS.items():
            embeddings = [
                self._sentence_transformer.encode([description], normalize_embeddings=True)[0]
                for description in descriptions
            ]
            embeddings_cache[symbol] = np.mean(embeddings, axis=0)
        return embeddings_cache

    def check_keypad_metrics(
        self, most_similar_score: float, non_correct_clusters: dict[str, float]
    ) -> bool:
        """Calculate contrast ratio and separation score."""
        similarity_ratio = most_similar_score / np.mean(list(non_correct_clusters.values())).item()

        return similarity_ratio > self.similarity_ratio_threshold

    def check_keypad_result(self, input_string: str, correct_symbol: str) -> bool:
        """Checks if the input aligns with the correct symbol based on similarity metrics."""
        input_embedding = self._sentence_transformer.encode(
            [input_string], normalize_embeddings=True
        )[0]

        cluster_similarities = {}
        for symbol, mean_embedding in self._keypad_cache.items():
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

    @weave.op
    @override
    def score(  # pyright: ignore[reportIncompatibleVariableOverride]
        self,
        output: PredictionOutput,
        ground_truth: str | list[str],
        input_type: TaskType,
        categories: list[str],
        **kwargs: Any,
    ) -> dict[str, bool | int | float] | None:
        """Score the keypad prediction."""
        if "module=keypad" not in categories:
            return None
        if input_type != "grounding":
            output_string = output["output"]

            if isinstance(ground_truth, list):
                ground_truth = ground_truth[0]

            is_correct = self.check_keypad_result(
                input_string=output_string, correct_symbol=ground_truth
            )
            score_output: dict[str, bool | int | float] | None = {"correct": is_correct}
            score_output[str(input_type)] = is_correct
            for category in categories:
                score_output[category] = is_correct
            return score_output

        return general_scorer(
            output=output, ground_truth=ground_truth, input_type=input_type, categories=categories
        )


# Create all the simple module scorers
score_timer = _create_module_scorer(module_name="timer")
score_wires = _create_module_scorer(module_name="wires")
score_wire_sequence = _create_module_scorer(module_name="wire_sequence")
score_venn = _create_module_scorer(module_name="venn")
score_maze = _create_module_scorer(module_name="maze")
score_button = _create_module_scorer(module_name="button")
score_simon_says = _create_module_scorer(module_name="simon")
score_memory = _create_module_scorer(module_name="memory")
score_password = _create_module_scorer(module_name="password")
score_whos_on_first = _create_module_scorer(module_name="whos_on_first")
score_morse_code = _create_module_scorer(module_name="morse_code")

# Create prefix-based scorers
score_detection = _create_prefix_scorer(prefix="detect", scorer_name="detection")
score_question_type = _create_prefix_scorer(prefix="question_type", scorer_name="question")
score_hallucination = _create_prefix_scorer(
    prefix="hallucination_type", scorer_name="hallucination"
)


def load_all_scorers() -> list[Op[..., Any] | weave.Scorer]:
    """Load all scorers."""
    keypad_scorer = KeypadScorer()
    keypad_scorer.load_model()
    return [
        score_timer,
        score_wires,
        score_wire_sequence,
        score_venn,
        score_maze,
        score_button,
        score_simon_says,
        score_memory,
        score_password,
        score_whos_on_first,
        score_morse_code,
        score_detection,
        score_question_type,
        score_hallucination,
        keypad_scorer,
    ]
