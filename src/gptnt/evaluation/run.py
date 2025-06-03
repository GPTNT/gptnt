import abc
import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, override

import datasets
import polars as pl
import structlog
import weave
from pydantic_ai import Agent
from tqdm import tqdm
from weave.flow.dataset import Dataset as WeaveDataset
from weave.trace.op import PostprocessInputsFunc

from gptnt.common.paths import Paths
from gptnt.dataset.expert_vqa import load_expert_vqa_dataset
from gptnt.evaluation.model import EvalModel, ModelOutput
from gptnt.evaluation.preprocess import (
    preprocess_expert_vqa_instance,
    preprocess_grounding_instance,
)
from gptnt.evaluation.scorers import ALL_SCORERS

logger = structlog.get_logger()
paths = Paths()


DEFAULT_INSTRUCTION = "Answer the following question based on the image. Output only the one word/number required to answer the question, nothing else."


def convert_hf_dataset_to_weave_dataset(
    hf_dataset: datasets.Dataset, task_name: str
) -> WeaveDataset:
    """Convert a Hugging Face dataset to a Weave dataset."""
    polars_df = datasets.Dataset.to_polars(self=hf_dataset)
    assert isinstance(polars_df, pl.DataFrame)
    polars_df = polars_df.with_row_index("index")
    weave_dataset = WeaveDataset(name=task_name, rows=weave.Table(polars_df.to_dicts()))
    return weave_dataset


def run_eval(
    *,
    preprocess_func: PostprocessInputsFunc,
    predict_method: Callable[..., ModelOutput],
    dataset: WeaveDataset,
    output_dir: Path,
) -> None:
    """Run the evaluation and save the outputs."""
    for idx, instance in enumerate(tqdm(dataset)):
        prediction_output_file = output_dir.joinpath(f"prediction_{idx}.json")
        if prediction_output_file.exists():
            logger.info(f"Skipping instance {idx}, output already exists.")
            continue

        preprocessed_instance = preprocess_func(instance)
        prediction = predict_method(**preprocessed_instance)
        # Add index to prediction content
        prediction_with_index = {"index": idx, **prediction}

        _ = prediction_output_file.write_text(json.dumps(prediction_with_index))


@dataclass(kw_only=True)
class RunEvaluation(abc.ABC):
    """Base class for running evaluations."""

    predict_method_name: ClassVar[str]
    """The specific predict method name to use for the evaluation from EvalModel."""

    preprocess_instance_func: PostprocessInputsFunc
    """The function to preprocess the instance before prediction."""

    agent: Agent
    task_name: str

    instructions: str = DEFAULT_INSTRUCTION
    weave_project: str = "gptnt/vqa"

    eval_model: EvalModel = field(init=False, repr=False)
    model_name: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the evaluation model."""
        self.eval_model = EvalModel.from_agent(agent=self.agent, instructions=self.instructions)
        assert isinstance(self.eval_model.name, str), "Model must have a name"
        self.model_name = self.eval_model.name
        self.eval_model.update_output_dir(self.output_dir)

    @property
    def output_dir(self) -> Path:
        """Get the output directory for the evaluation results."""
        output_dir = paths.output.joinpath(f"{self.task_name}_predictions", self.model_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    @abc.abstractmethod
    def load_dataset(self) -> WeaveDataset:
        """Load the dataset as a Weave dataset."""
        raise NotImplementedError("Subclasses must implement load_dataset method.")

    def throw(self) -> None:
        """Run the evaluation."""
        weave_client = weave.init(self.weave_project)
        assert getattr(self.eval_model, self.predict_method_name, None) is not None, (
            "EvalModel must have the specified predict method"
        )
        logger.info(f"Running grounding evaluation for task: {self.task_name}")
        run_eval(
            preprocess_func=self.preprocess_instance_func,
            predict_method=getattr(self.eval_model, self.predict_method_name),
            dataset=self.load_dataset(),
            output_dir=self.output_dir,
        )
        weave_client.finish()

    def upload(self) -> None:
        """Upload the evaluation results to Weave."""
        weave_client = weave.init(self.weave_project)
        dataset = self.load_dataset()
        evaluation = weave.Evaluation(
            dataset=dataset,
            scorers=list(ALL_SCORERS),
            preprocess_model_input=self.preprocess_instance_func,
        )
        asyncio.run(evaluation.evaluate(self.eval_model))
        weave_client.finish()


@dataclass(kw_only=True)
class RunGroundingEvaluation(RunEvaluation):
    """Run the grounding evaluation."""

    hf_dataset_name: str = "GPTNT/grounding-dataset"
    task_name: str = "grounding"

    preprocess_instance_func: PostprocessInputsFunc = preprocess_grounding_instance
    predict_method_name = "grounding_predict"

    @override
    def load_dataset(self) -> WeaveDataset:
        """Load the dataset as a Weave dataset."""
        dataset = datasets.load_dataset(self.hf_dataset_name, split="test")
        assert isinstance(dataset, datasets.Dataset), "Dataset must be of type datasets.Dataset"
        weave_dataset = convert_hf_dataset_to_weave_dataset(dataset, self.task_name)
        return weave_dataset


@dataclass(kw_only=True)
class RunExpertVQAEvaluation(RunEvaluation):
    """Run the expert VQA evaluation."""

    task_name: str = "expert_vqa"

    preprocess_instance_func: PostprocessInputsFunc = preprocess_expert_vqa_instance
    predict_method_name = "expert_vqa_predict"

    @override
    def load_dataset(self) -> WeaveDataset:
        """Load the dataset as a Weave dataset."""
        dataset = load_expert_vqa_dataset()
        weave_dataset = WeaveDataset(name=self.task_name, rows=weave.Table(dataset))  # pyright: ignore[reportArgumentType]
        return weave_dataset
