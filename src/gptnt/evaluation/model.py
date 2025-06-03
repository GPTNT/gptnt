import io
import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Self, TypedDict

import structlog
import weave
from PIL import Image
from pydantic.fields import PrivateAttr
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent
from pydantic_ai.models import Model
from weave.flow.model import Model as WeaveModel

from gptnt.common.paths import Paths

if TYPE_CHECKING:
    from pydantic_ai.agent import AgentRunResult


logger = structlog.get_logger()
paths = Paths()


class ModelOutput(TypedDict):
    """Output of the model predict."""

    usage: dict[Literal["input_tokens", "output_tokens", "total_tokens"], int]
    model: str
    output: str


class EvalModel(WeaveModel):
    """Perform the evaluation on PydanticAI models."""

    _agent: Agent = PrivateAttr()
    """PydanticAI Agent to be used for evaluation."""

    _output_dir: Path = PrivateAttr()
    """Directory to save the evaluation outputs."""

    @classmethod
    def from_agent(cls, *, agent: Agent, instructions: str) -> Self:
        """Create an EvalModel from a PydanticAI Agent."""
        agent._instructions = instructions  # noqa: SLF001

        model_name = None
        if isinstance(agent.model, str):
            model_name = agent.model
        if isinstance(agent.model, Model):
            model_name = agent.model.model_name

        assert isinstance(model_name, str), "Model name must be a string"
        model_name = model_name.replace("eu.", "")
        eval_model = cls(name=model_name)
        eval_model._agent = agent
        return eval_model

    def update_output_dir(self, output_dir: Path) -> None:
        """Update the output directory for the model."""
        self._output_dir = output_dir

    @weave.op
    def grounding_predict(self, model_input: str, som_image: Image.Image) -> ModelOutput:
        """Run the model on the input."""
        buffer = io.BytesIO()
        som_image.save(buffer, format="PNG")
        binary_image = BinaryContent(data=buffer.getvalue(), media_type="image/png")
        model_output: AgentRunResult[str] = self._agent.run_sync([binary_image, model_input])

        # TODO: Remove any possible symbols or characters that are not valid in the output
        output_string = model_output.output.strip()
        return ModelOutput(
            usage={
                "input_tokens": model_output.usage().request_tokens or 0,
                "output_tokens": model_output.usage().response_tokens or 0,
                "total_tokens": model_output.usage().total_tokens or 0,
            },
            model=self.name or "",
            output=output_string,
        )

    @weave.op
    def expert_vqa_predict(self, model_input: str, manual: list[str | Image.Image]) -> ModelOutput:
        """Run the model on the input."""
        loaded_manual: list[str | BinaryContent] = []
        for page in manual:
            if isinstance(page, Image.Image):
                buffer = io.BytesIO()
                page.save(buffer, format="PNG")
                binary_image = BinaryContent(data=buffer.getvalue(), media_type="image/png")
                loaded_manual.append(binary_image)
            else:
                loaded_manual.append(page)

        model_output: AgentRunResult[str] = self._agent.run_sync([*loaded_manual, model_input])
        output_string = model_output.output.strip()
        return ModelOutput(
            usage={
                "input_tokens": model_output.usage().request_tokens or 0,
                "output_tokens": model_output.usage().response_tokens or 0,
                "total_tokens": model_output.usage().total_tokens or 0,
            },
            model=self.name or "",
            output=output_string,
        )

    @weave.op
    def predict(self, index: int) -> ModelOutput:
        """Fetch the model answer from the json."""
        prediction_path = self._output_dir.joinpath(f"prediction_{index}.json")

        # Read and return the contents of the file
        with (prediction_path).open("r", encoding="utf-8") as pred_file:
            return json.load(fp=pred_file)
