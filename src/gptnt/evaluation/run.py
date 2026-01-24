import abc
import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, override

import datasets
import numpy as np
import polars as pl
import structlog
import weave
from PIL import Image
from pydantic_ai import Agent
from tqdm import tqdm
from weave import Dataset as WeaveDataset
from weave.flow.casting import ScorerLike

from gptnt.common.paths import Paths
from gptnt.evaluation.model import EvalModel, ModelOutput
from gptnt.evaluation.preprocess import PostprocessInputsFunc
from gptnt.processors.image_resizer import ImageResizer

logger = structlog.get_logger()
paths = Paths()


OPEN_ENDED_INSTRUCTION = "Answer the following question based on given context. Output only the one letter, word, short phrase, or number required to answer the question, nothing else."
MCQ_INSTRUCTION = "Answer the following multiple choice question based on the given context. Output only the letter of the correct answer, nothing else."
OCR_INSTRUCTION = "Follow the instruction given the context from the image. Output only the answer, nothing else."

GROUNDING_SOM_PROMPT = "The image contains objects annotated with alphabetical markers positioned beside each object. When asked about an object's location, respond only with the corresponding letter. If multiple objects match, respond with 'More information needed'. If no such object exists, respond with 'None'."

GROUNDING_COORDINATES_PROMPT = 'The resolution of the image is {IMAGE_WIDTH}x{IMAGE_HEIGHT}. Coordinates (x, y) are absolute pixel positions with (0,0) at the top-left and ({IMAGE_WIDTH},{IMAGE_HEIGHT}) at the bottom-right. When asked about an object\'s location, respond with coordinates of any point within the object. Format: {"x": <int>, "y": <int>}. If multiple objects match, respond with "More information needed". If no such object exists, respond with "None".'


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


def _resize_instance_items(
    element: Any | dict[str, Any] | list[Any], *, image_resizer: ImageResizer
) -> Any:
    if isinstance(element, Image.Image):
        return image_resizer.resize_image(element)

    if isinstance(element, np.ndarray):
        return image_resizer.resize_array(element)

    # 2. Recurse through Dictionaries
    if isinstance(element, dict):
        return {
            k: _resize_instance_items(v, image_resizer=image_resizer)
            for k, v in element.items()  # noqa: WPS111
        }

    # 3. Recurse through Lists
    if isinstance(element, list):
        return [_resize_instance_items(i, image_resizer=image_resizer) for i in element]  # noqa: WPS111

    # 4. Return primitives/other objects unchanged
    return element


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

    weave_project: str
    weave_scorers: list[ScorerLike]

    eval_model: EvalModel = field(init=False, repr=False)
    model_name: str = field(init=False, repr=False)

    image_resizer: ImageResizer

    max_instances: int | None = None
    """Maximum number of instances to evaluate on."""

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
        """Load the dataset as a Weave dataset.

        You should also resize all the images.
        """
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
        evaluation = weave.Evaluation(dataset=dataset, scorers=self.weave_scorers)
        asyncio.run(evaluation.evaluate(self.eval_model))
        weave_client.finish()

    def _resize_all_images(self, all_instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Inelegantly, resize every image across every instance."""
        # TODO: Optimize this later if needed
        fixed_instances = [
            _resize_instance_items(instance, image_resizer=self.image_resizer)
            for instance in tqdm(all_instances, desc="Resize images")
        ]
        return fixed_instances


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
        if self.max_instances is not None:
            instances = instances[: self.max_instances]
        instances = list(
            tqdm(
                map(self.preprocess_instance_func, instances),
                total=len(instances),
                desc="Preprocessing instances",
            )
        )
        instances = self._resize_all_images(instances)
        weave_dataset = WeaveDataset(name=self.task_name, rows=weave.Table(instances))
        return weave_dataset
