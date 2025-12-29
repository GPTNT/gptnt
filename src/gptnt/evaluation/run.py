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

from gptnt.common.paths import Paths
from gptnt.dataset.defuser_vqa.constants import TaskType
from gptnt.evaluation.model import EvalModel, ModelOutput
from gptnt.evaluation.preprocess import PostprocessInputsFunc
from gptnt.evaluation.scorers import load_all_scorers

logger = structlog.get_logger()
paths = Paths()


DEFAULT_INSTRUCTION = "Answer the following question based on given context. Output only the one letter, word, short phrase, or number required to answer the question, nothing else."
MCQ_INSTRUCTION = "Answer the following multiple choice question based on the given context. Output only the letter of the correct answer, nothing else."
OCR_INSTRUCTION = "Follow the instruction given the context from the image. Output only the answer, nothing else."


def convert_hf_dataset_to_instances(
    hf_dataset: datasets.Dataset | datasets.DatasetDict,
) -> list[dict[str, Any]]:
    """Convert a Hugging Face dataset to just its instances."""
    # Handle DatasetDict by merging all splits into one too
    if isinstance(hf_dataset, datasets.DatasetDict):
        all_datasets = list(hf_dataset.values())
    else:
        all_datasets = [hf_dataset]

    previous_start_index = 0
    all_polar_dfs: list[pl.DataFrame] = []
    for ds in all_datasets:
        polars_df = datasets.Dataset.to_polars(self=ds)
        assert isinstance(polars_df, pl.DataFrame)

        polars_df = polars_df.with_row_index("index", offset=previous_start_index)
        previous_start_index += polars_df.height
        all_polar_dfs.append(polars_df)

    return [element for df in all_polar_dfs for element in df.to_dicts()]


@weave.op
def run_eval_step(
    *,
    instance: dict[str, Any],
    predict_method: Callable[..., ModelOutput],
    prediction_output_file: Path,
) -> ModelOutput | None:
    """Run a single evaluation step for an instance."""
    prediction = predict_method(**instance)
    # Add index to prediction content
    prediction_with_index = {"index": instance["index"], **prediction}
    _ = prediction_output_file.write_text(json.dumps(prediction_with_index))
    return prediction


@dataclass(kw_only=True)
class RunEvaluation(abc.ABC):
    """Base class for running evaluations."""

    predict_method_name: ClassVar[str] = "model_predict"
    """The specific predict method name to use for the evaluation from EvalModel."""

    agent: Agent
    task_name: str
    task_type: TaskType

    weave_project: str

    eval_model: EvalModel = field(init=False, repr=False)
    model_name: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the evaluation model."""
        self.eval_model = EvalModel.from_agent(agent=self.agent)
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
            dataset=dataset, scorers=load_all_scorers(task_type=self.task_type)
        )
        asyncio.run(evaluation.evaluate(self.eval_model))
        weave_client.finish()


@dataclass(kw_only=True)
class RunHFDatasetEvaluation(RunEvaluation):
    """Run the evaluation on a huggingface dataset."""

    hf_repo_id: str
    """Get the HF dataset repo identifier."""

    dataset_split: str | None = None

    preprocess_instance_func: PostprocessInputsFunc
    """The function to preprocess the instance before loading into the WeaveDataset."""

    @override
    def load_dataset(self) -> WeaveDataset:
        """Load the dataset as a Weave dataset."""
        dataset = datasets.load_dataset(self.hf_repo_id, split=self.dataset_split)

        assert isinstance(dataset, (datasets.Dataset, datasets.DatasetDict))
        instances = convert_hf_dataset_to_instances(dataset)
        instances = list(
            tqdm(
                map(self.preprocess_instance_func, instances),
                total=len(instances),
                desc="Preprocessing instances",
            )
        )
        weave_dataset = WeaveDataset(name=self.task_name, rows=weave.Table(instances))
        return weave_dataset
