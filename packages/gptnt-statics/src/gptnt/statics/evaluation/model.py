import io
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Self, TypedDict

import structlog
from PIL import Image
from pydantic import BaseModel
from pydantic.fields import PrivateAttr
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent
from pydantic_ai.models import Model
from structlog.tracebacks import ExceptionDictTransformer

from gptnt.core.common.paths import Paths
from gptnt.core.players.action_predictor import execute_request
from gptnt.core.players.reasoning_parser.reasoning_parser import ReasoningParser

logger = structlog.get_logger()
paths = Paths()


_exception_transformer = ExceptionDictTransformer(
    use_rich=False, show_locals=False, locals_max_string=200, locals_max_length=10
)


class ModelOutput(TypedDict):
    """Output of the model predict."""

    usage: dict[str, int]
    model: str
    output: str
    thoughts: str | None
    raw_output: str | None
    error: str | None
    """Log any response errors that occurred during prediction."""

    exception: Any | None
    """Log any exception that occurred during prediction."""


class EvalModel(BaseModel):
    """Perform the evaluation on PydanticAI models."""

    name: str | None = None
    """Model name, used for output paths and result labelling."""

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

    async def model_predict(  # noqa: WPS210
        self,
        model_input: list[str | Image.Image],
        *args: Any,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> ModelOutput:
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

        try:
            model_output = await execute_request(
                loaded_inputs,
                agent=self._agent,
                reasoning_parser=self._reasoning_parser,
                deps=None,
                message_history=None,
                model_output_type=str,
                parser_output_type=None,
            )
        except Exception as exc:
            logger.exception("Model prediction failed")
            response_errors = getattr(exc, "response_error", None)
            return ModelOutput(
                usage={},
                model=self.name or "",
                output="",
                thoughts=None,
                raw_output=getattr(exc, "output", None),
                error=str(response_errors) if response_errors else None,
                exception=_exception_transformer(sys.exc_info()),  # pyright: ignore[reportArgumentType]
            )

        # Flatten all the usage and remove zero counts
        usage: dict[str, int] = {}
        for token_type, token_count in asdict(model_output.usage).items():
            if isinstance(token_count, dict):
                usage.update(token_count)
            else:
                usage[token_type] = token_count
        usage = {token: count for token, count in usage.items() if count > 0}

        return ModelOutput(
            usage=usage,
            model=self.name or "",
            output=model_output.output,
            thoughts=model_output.thoughts,
            raw_output=model_output.raw_output,
            error=str(model_output.ai_response_error) if model_output.ai_response_error else None,
            exception=None,
        )

    def predict(self, index: int, model_input: Any, *args: Any, **kwargs: Any) -> ModelOutput:  # noqa: ARG002
        """Fetch the model answer from the json."""
        prediction_path = self._output_dir.joinpath(f"prediction_{index}.json")

        # Read and return the contents of the file
        with (prediction_path).open("r", encoding="utf-8") as pred_file:
            return json.load(fp=pred_file)
