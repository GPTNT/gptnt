import abc
import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, override

import datasets
import polars as pl
import structlog
import weave
from pydantic_ai import Agent
from tqdm import tqdm
from weave import Dataset as WeaveDataset
from weave.trace.op import PostprocessInputsFunc

from gptnt.common.paths import Paths
from gptnt.dataset.defuser_vqa.constants import TaskFormat, TaskType
from gptnt.dataset.expert_vqa import load_expert_vqa_dataset
from gptnt.evaluation.model import EvalModel, ModelOutput
from gptnt.evaluation.preprocess import (
    preprocess_defuser_vqa_mcq_instance,
    preprocess_defuser_vqa_open_ended_instance,
    preprocess_expert_vqa_instance,
    preprocess_grounding_instance,
)
from gptnt.evaluation.scorers import load_all_scorers

logger = structlog.get_logger()
paths = Paths()


DEFAULT_INSTRUCTION = "Answer the following question based on given context. Output only the one letter, word short phrase, or number required to answer the question, nothing else."
MCQ_INSTRUCTION = "Answer the following multiple choice question based on the given context. Output only the letter of the correct answer, nothing else."


def convert_hf_dataset_to_weave_dataset(
    hf_dataset: datasets.Dataset, task_name: TaskType, task_format: TaskFormat
) -> WeaveDataset:
    """Convert a Hugging Face dataset to a Weave dataset."""
    polars_df = datasets.Dataset.to_polars(self=hf_dataset)
    assert isinstance(polars_df, pl.DataFrame)
    polars_df = polars_df.with_row_index("index").filter(
        (pl.col("input_type") == task_name) & (pl.col("question_format") == task_format)
    )
    weave_dataset = WeaveDataset(name=task_name, rows=weave.Table(polars_df.to_dicts()))
    return weave_dataset


@weave.op
def run_eval_step(
    *,
    instance: dict[str, Any],
    preprocess_func: PostprocessInputsFunc,
    predict_method: Callable[..., ModelOutput],
    prediction_output_file: Path,
) -> ModelOutput | None:
    """Run a single evaluation step for an instance."""
    preprocessed_instance = preprocess_func(instance)
    prediction = predict_method(**preprocessed_instance)
    # Add index to prediction content
    prediction_with_index = {"index": instance["index"], **prediction}
    _ = prediction_output_file.write_text(json.dumps(prediction_with_index))
    return prediction


@dataclass(kw_only=True)
class RunEvaluation(abc.ABC):
    """Base class for running evaluations."""

    predict_method_name: ClassVar[str]
    """The specific predict method name to use for the evaluation from EvalModel."""

    preprocess_instance_func: PostprocessInputsFunc
    """The function to preprocess the instance before prediction."""

    agent: Agent
    task_name: TaskType
    weave_project: str

    task_format: TaskFormat = "open_ended"
    instructions: str = DEFAULT_INSTRUCTION

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
        logger.info(f"Running evaluation for task: {self.task_name}")
        for instance in tqdm(self.load_dataset()):
            prediction_output_file = self.output_dir.joinpath(
                f"prediction_{instance['index']}.json"
            )
            if prediction_output_file.exists():
                logger.info(f"Skipping instance {instance['index']}, output already exists.")
                continue
            _ = run_eval_step(
                instance=instance,
                preprocess_func=self.preprocess_instance_func,
                predict_method=getattr(self.eval_model, self.predict_method_name),
                prediction_output_file=prediction_output_file,
            )
        logger.info(f"Evaluation completed. Results saved to {self.output_dir}")
        weave_client.finish()

    def upload(self) -> None:
        """Upload the evaluation results to Weave."""
        weave_client = weave.init(self.weave_project)
        dataset = self.load_dataset()
        evaluation = weave.Evaluation(
            dataset=dataset,
            scorers=load_all_scorers(task_type=self.task_name),
            preprocess_model_input=self.preprocess_instance_func,
        )
        asyncio.run(evaluation.evaluate(self.eval_model))
        weave_client.finish()


@dataclass(kw_only=True)
class RunHFDatasetEvaluation(RunEvaluation):
    """Run the evaluation on a huggingface dataset."""

    hf_dataset_name: str

    @override
    def load_dataset(self) -> WeaveDataset:
        """Load the dataset as a Weave dataset."""
        dataset = datasets.load_dataset(self.hf_dataset_name, split="test")
        assert isinstance(dataset, datasets.Dataset), "Dataset must be of type datasets.Dataset"
        weave_dataset = convert_hf_dataset_to_weave_dataset(
            dataset, self.task_name, self.task_format
        )
        return weave_dataset


@dataclass(kw_only=True)
class RunGroundingEvaluation(RunHFDatasetEvaluation):
    """Run the grounding evaluation."""

    hf_dataset_name: str = "GPTNT/defuser-vqa-and-grounding-dataset"
    task_name: TaskType = "grounding"
    weave_project: str = "gptnt/grounding"

    preprocess_instance_func: PostprocessInputsFunc = preprocess_grounding_instance
    predict_method_name = "grounding_predict"


@dataclass(kw_only=True)
class RunDefuserVQAOpenEndedEvaluation(RunGroundingEvaluation):
    """Run the defuser VQA evaluation on open-ended questions."""

    task_name: TaskType = "vqa"
    weave_project: str = "gptnt/defuser-vqa-open_ended"

    preprocess_instance_func: PostprocessInputsFunc = preprocess_defuser_vqa_open_ended_instance
    predict_method_name = "defuser_vqa_open_ended_predict"


@dataclass(kw_only=True)
class RunDefuserVQAMCQEvaluation(RunGroundingEvaluation):
    """Run the defuser VQA evaluation on multiple-choice questions."""

    task_name: TaskType = "vqa"
    task_format: TaskFormat = "multiple_choice"
    instructions = MCQ_INSTRUCTION
    weave_project: str = "gptnt/defuser-vqa-mcq"

    preprocess_instance_func: PostprocessInputsFunc = preprocess_defuser_vqa_mcq_instance
    predict_method_name = "defuser_vqa_open_ended_predict"


@dataclass(kw_only=True)
class RunExpertVQAEvaluation(RunEvaluation):
    """Run the expert VQA evaluation."""

    task_name: TaskType = "expert_vqa"

    instructions = MCQ_INSTRUCTION
    weave_project: str = "gptnt/expert-vqa"
    preprocess_instance_func: PostprocessInputsFunc = preprocess_expert_vqa_instance
    predict_method_name = "expert_vqa_predict"

    @override
    def load_dataset(self) -> WeaveDataset:
        """Load the dataset as a Weave dataset."""
        dataset = load_expert_vqa_dataset()
        weave_dataset = WeaveDataset(name=self.task_name, rows=weave.Table(dataset))  # pyright: ignore[reportArgumentType]
        return weave_dataset
