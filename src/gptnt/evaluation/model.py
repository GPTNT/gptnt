import io
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Self, TypedDict

import structlog
import weave
from PIL import Image
from pydantic.fields import PrivateAttr
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent
from pydantic_ai.models import Model
from weave.flow.model import Model as WeaveModel

from gptnt.common.paths import Paths
from gptnt.players.reasoning_parser.reasoning_parser import ReasoningParser

if TYPE_CHECKING:
    from pydantic_ai.agent import AgentRunResult

    from gptnt.players.actions import AgentCallResult


logger = structlog.get_logger()
paths = Paths()


class ModelOutput(TypedDict):
    """Output of the model predict."""

    usage: dict[Literal["input_tokens", "output_tokens", "total_tokens"], int]
    model: str
    output: str
    thoughts: str | None
    raw_output: str | None


class EvalModel(WeaveModel):
    """Perform the evaluation on PydanticAI models."""

    _agent: Agent = PrivateAttr()
    """PydanticAI Agent to be used for evaluation."""

    _output_dir: Path = PrivateAttr()
    """Directory to save the evaluation outputs."""

    _reasoning_parser: ReasoningParser[Any, Any] = PrivateAttr()

    @classmethod
    def from_agent(cls, *, agent: Agent) -> Self:
        """Create an EvalModel from a PydanticAI Agent and their capabilities.

        Capabilities are there so that we can grab/check for model-specific settings.
        """
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

    def update_reasoning_parser(self, reasoning_parser: ReasoningParser[Any, Any]) -> None:
        """Update the reasoning parser for the model."""
        self._reasoning_parser = reasoning_parser
        self._reasoning_parser.structure_output = False

    @weave.op
    def model_predict(self, model_input: list[str | Image.Image], **kwargs: Any) -> ModelOutput:  # noqa: ARG002
        """Run the model on the input."""
        loaded_inputs: list[BinaryContent | str] = []
        for chunk in model_input:
            if isinstance(chunk, Image.Image):
                buffer = io.BytesIO()
                chunk.save(buffer, format="PNG")
                binary_image = BinaryContent(data=buffer.getvalue(), media_type="image/png")
                loaded_inputs.append(binary_image)
            else:
                loaded_inputs.append(chunk)

        model_output: AgentRunResult[str] = self._agent.run_sync(loaded_inputs)
        parsed_output: AgentCallResult[str] = self._reasoning_parser(model_output, output_type=str)
        return ModelOutput(
            usage={
                "input_tokens": model_output.usage().input_tokens or 0,
                "output_tokens": model_output.usage().output_tokens or 0,
                "total_tokens": model_output.usage().total_tokens or 0,
            },
            model=self.name or "",
            output=parsed_output.output,
            thoughts=parsed_output.thoughts,
            raw_output=parsed_output.raw_output,
        )

    @weave.op
    def predict(self, index: int, model_input: Any, **kwargs: Any) -> ModelOutput:  # noqa: ARG002
        """Fetch the model answer from the json."""
        prediction_path = self._output_dir.joinpath(f"prediction_{index}.json")

        # Read and return the contents of the file
        with (prediction_path).open("r", encoding="utf-8") as pred_file:
            return json.load(fp=pred_file)
