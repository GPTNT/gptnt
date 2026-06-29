"""Tests for the local (Weave-free) metrics aggregation: `score_predictions`.

This is the path that replaced Weave-orchestrated scoring (statics can compute metrics with the
`weave` extra uninstalled). A lightweight comparer keeps the test fast — no model/dataset.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, override

from gptnt.statics.scorers import (
    BaseComparer,
    CategoryPrefixScorer,
    ModuleScorer,
    score_predictions,
)

if TYPE_CHECKING:
    from gptnt.statics.scorers import PredictionOutput


@dataclass(kw_only=True)
class _ExactMatchComparer(BaseComparer[str, bool]):
    """Trivial comparer: the prediction is correct iff it equals the ground truth string."""

    @override
    def __call__(self, output: PredictionOutput, ground_truth: str, *, module: str) -> bool:
        return output["output"] == ground_truth


def test_module_scorer_averages_numeric_scores() -> None:
    scorer = ModuleScorer(name="module", comparer=_ExactMatchComparer(task_type=None))
    instances = [
        {"index": 0, "ground_truth": "yes", "categories": ["module=wires"]},
        {"index": 1, "ground_truth": "no", "categories": ["module=wires"]},
    ]
    predictions = {0: {"output": "yes"}, 1: {"output": "wrong"}}

    metrics = score_predictions([scorer], instances, predictions)

    # One of two correct -> 0.5 overall and 0.5 for the wires module slice.
    assert metrics["module"]["total"] == Decimal("0.5")
    assert metrics["module"]["wires"] == Decimal("0.5")


def test_category_prefix_scorer_slices_by_prefix() -> None:
    scorer = CategoryPrefixScorer(
        name="question_type", prefix="question_type", comparer=_ExactMatchComparer(task_type=None)
    )
    instances = [
        {"index": 0, "ground_truth": "a", "categories": ["module=keypad", "question_type=count"]},
        {"index": 1, "ground_truth": "b", "categories": ["module=keypad", "question_type=count"]},
    ]
    predictions = {0: {"output": "a"}, 1: {"output": "b"}}

    metrics = score_predictions([scorer], instances, predictions)

    assert metrics["question_type"]["count.total"] == Decimal("1.0")
    assert metrics["question_type"]["count.module.keypad"] == Decimal("1.0")


def test_trick_questions_are_skipped() -> None:
    scorer = ModuleScorer(name="module", comparer=_ExactMatchComparer(task_type=None))
    instances = [
        {
            "index": 0,
            "ground_truth": "x",
            "categories": ["module=wires", "hallucination_type=type_a"],
        }
    ]
    predictions = {0: {"output": "x"}}

    metrics = score_predictions([scorer], instances, predictions)

    assert not metrics["module"]


def test_missing_predictions_are_ignored() -> None:
    scorer = ModuleScorer(name="module", comparer=_ExactMatchComparer(task_type=None))
    instances = [
        {"index": 0, "ground_truth": "yes", "categories": ["module=wires"]},
        {"index": 1, "ground_truth": "yes", "categories": ["module=wires"]},
    ]
    predictions = {0: {"output": "yes"}}  # index 1 has no prediction

    metrics = score_predictions([scorer], instances, predictions)

    assert metrics["module"]["total"] == Decimal("1.0")
