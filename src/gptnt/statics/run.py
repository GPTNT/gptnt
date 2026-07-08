import abc
import importlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, override

import datasets
import numpy as np
import polars as pl
import structlog
from PIL import Image
from pydantic_ai import Agent
from tqdm import tqdm

from gptnt.common.paths import Paths
from gptnt.players.reasoning_parser.inner_monologue import InnerMonologueReasoningParser
from gptnt.players.reasoning_parser.react import ReactStyleReasoningParser
from gptnt.players.specification import PlayerCapabilities
from gptnt.processors.image_resizer import ImageResizer
from gptnt.statics.model import EvalModel, ModelOutput
from gptnt.statics.preprocess import PostprocessInputsFunc
from gptnt.statics.run_metadata import StaticsIdentity, StaticsRunMetadata
from gptnt.statics.scorers import Instances, Metrics, Predictions, Scorer, score_predictions

logger = structlog.get_logger()
paths = Paths()


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


async def run_eval_step(
    *,
    instance: dict[str, Any],
    predict_method: Callable[..., Awaitable[ModelOutput]],
    prediction_output_file: Path,
) -> ModelOutput | None:
    """Run a single evaluation step for an instance."""
    prediction = await predict_method(**instance)
    # Add index to prediction content
    prediction_with_index = {"index": instance["index"], **prediction}
    _ = prediction_output_file.write_text(json.dumps(prediction_with_index))  # noqa: ASYNC240
    return prediction


@dataclass(kw_only=True)
class RunEvaluation(abc.ABC):
    """Base class for running evaluations."""

    predict_method_name: ClassVar[str] = "model_predict"
    """The specific predict method name to use for the evaluation from EvalModel."""

    agent: Agent
    capabilities: PlayerCapabilities

    task_name: str

    weave_project: str
    scorers: list[Scorer]

    image_resizer: ImageResizer

    eval_model: EvalModel = field(init=False, repr=False)
    model_name: str = field(init=False, repr=False)

    max_instances: int | None = None
    """Maximum number of instances to evaluate on."""

    def __post_init__(self) -> None:
        """Initialize the evaluation model."""
        self.eval_model = EvalModel.from_agent(agent=self.agent)
        assert isinstance(self.eval_model.name, str), "Model must have a name"
        self.model_name = self.eval_model.name
        self.eval_model.update_output_dir(self.output_dir)
        self.eval_model.update_reasoning_parser(
            InnerMonologueReasoningParser()
            if self.capabilities.thinking_method == "inner-monologue"
            else ReactStyleReasoningParser()
        )

    @property
    def output_dir(self) -> Path:
        """Get the output directory for the evaluation results."""
        output_dir = paths.output.joinpath(f"{self.task_name}_predictions", self.model_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    @property
    def instructions(self) -> str:
        """Get the instructions for the evaluation.

        Because we don't want to care, we only support literal instructions here.
        """
        literal_instructions, functional_instructions = self.agent._get_instructions()  # noqa: SLF001
        if functional_instructions:
            raise ValueError("Functional instructions are not supported in RunEvaluation.")
        assert literal_instructions is not None, "Instructions must be provided."
        return literal_instructions

    @abc.abstractmethod
    def load_dataset(self) -> list[dict[str, Any]]:
        """Load and preprocess the dataset into a list of instances (resizing images)."""
        raise NotImplementedError("Subclasses must implement load_dataset method.")

    async def throw(self) -> None:
        """Run predictions for every instance, then compute and write local metrics (no Weave)."""
        assert getattr(self.eval_model, self.predict_method_name, None) is not None, (
            "EvalModel must have the specified predict method"
        )
        logger.info(f"Running evaluation for task: {self.task_name}")
        instances = self.load_dataset()
        for instance in tqdm(instances):
            prediction_output_file = self.output_dir.joinpath(
                f"prediction_{instance['index']}.json"
            )
            if prediction_output_file.exists():
                logger.info(f"Skipping instance {instance['index']}, output already exists.")
                continue

            _ = await run_eval_step(  # noqa: WPS476
                instance=instance,
                predict_method=getattr(self.eval_model, self.predict_method_name),
                prediction_output_file=prediction_output_file,
            )

        _ = self.score(instances)
        logger.info(f"Evaluation completed. Results saved to {self.output_dir}")

    def score(self, instances: Instances | None = None) -> Metrics:
        """Compute metrics locally from the saved predictions and write metrics.json (no Weave)."""
        if instances is None:
            instances = self.load_dataset()
        predictions: Predictions = {}
        for instance in instances:
            prediction_file = self.output_dir.joinpath(f"prediction_{instance['index']}.json")
            predictions[instance["index"]] = json.loads(prediction_file.read_text())
        metrics = score_predictions(self.scorers, instances, predictions)
        metrics_file = self.output_dir.joinpath("metrics.json")
        _ = metrics_file.write_text(json.dumps(metrics, indent=2))
        logger.info(f"Wrote metrics for {len(predictions)} predictions to {metrics_file}")
        return metrics

    async def upload(self) -> None:
        """Publish predictions + local metrics to Weave.

        Requires the `weave` optional extra.
        """
        try:
            weave: Any = importlib.import_module("weave")
        except ImportError as exc:
            raise RuntimeError(
                "Weave is not installed. Install `gptnt-statics[weave]` to use --upload."
            ) from exc
        weave_client = weave.init(self.weave_project)
        metrics = self.score()
        _ = weave.publish(metrics, name=f"{self.task_name}-{self.model_name}-metrics")
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

    revision: str | None = None
    """Dataset revision to pin (a branch, tag, or commit sha); `None` loads the default branch."""

    preprocess_instance_func: PostprocessInputsFunc
    """The function to preprocess the instance before loading into the WeaveDataset."""

    def write_run_metadata(self) -> None:
        """Stamp `run_meta.json` beside the metrics so the outputs are self-describing."""
        metadata = StaticsRunMetadata(
            model_name=self.model_name,
            statics=StaticsIdentity.resolve(
                task_name=self.task_name,
                hf_repo_id=self.hf_repo_id,
                dataset_split=self.dataset_split,
                revision=self.revision,
            ),
            capabilities=self.capabilities,
        )
        metadata_file = self.output_dir.joinpath("run_meta.json")
        _ = metadata_file.write_text(metadata.model_dump_json(indent=2))

    @override
    async def throw(self) -> None:
        """Run predictions and metrics, then stamp the run metadata beside them."""
        await super().throw()
        self.write_run_metadata()

    @override
    def load_dataset(self) -> list[dict[str, Any]]:
        """Load and preprocess the HuggingFace dataset into a list of instances."""
        dataset = datasets.load_dataset(
            self.hf_repo_id, split=self.dataset_split, revision=self.revision
        )

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
        instances = [{**instance, "instructions": self.instructions} for instance in instances]
        return self._resize_all_images(instances)
