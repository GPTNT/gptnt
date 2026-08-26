import io
import sys
from collections.abc import Callable
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
from pydantic_core import from_json
from structlog.tracebacks import ExceptionDictTransformer

from gptnt.common.paths import Paths
from gptnt.players.action_predictor import execute_request
from gptnt.players.reasoning_parser.reasoning_parser import ReasoningParser

logger = structlog.get_logger()
paths = Paths()


_exception_transformer = ExceptionDictTransformer(
    use_rich=False, show_locals=False, locals_max_string=200, locals_max_length=10
)


class ModelOutput(TypedDict):
    """Output of the model predict."""

    usage: dict[str, int]
    """Non-zero Pydantic AI token-usage counts flattened for this prediction."""

    model: str
    """Provider model name resolved for this prediction."""

    output: str
    """Parsed task output before task-specific score normalisation."""

    scored_output: str
    """Canonical task answer consumed by scorers."""

    thoughts: str | None
    raw_output: str | None
    error: str | None
    """Model-response validation classifications produced by parsing or recovery."""

    exception: Any | None
    """Structured traceback for an exception that prevented prediction."""


class EvalModel(BaseModel):
    """Perform the evaluation on PydanticAI models."""

    name: str | None = None
    """Model name, used for output paths and result labelling."""

    _agent: Agent = PrivateAttr()
    """PydanticAI Agent to be used for evaluation."""

    _output_dir: Path = PrivateAttr()
    """Directory to save the evaluation outputs."""

    _reasoning_parser: ReasoningParser[Any, Any] = PrivateAttr()
    _model_output_type: Any = PrivateAttr(default=str)
    _output_serializer: Callable[[Any], str] = PrivateAttr(default=str)
    _scored_output_func: Callable[[dict[str, Any]], str] = PrivateAttr()

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

    def update_output_contract(
        self, *, model_output_type: Any, output_serializer: Callable[[Any], str]
    ) -> None:
        """Set the task-specific model output type and its storage serializer."""
        self._model_output_type = model_output_type
        self._output_serializer = output_serializer

    def update_scored_output_func(self, func: Callable[[dict[str, Any]], str]) -> None:
        """Set the task normalizer used to populate `scored_output`."""
        self._scored_output_func = func

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
                model_output_type=self._model_output_type,
                parser_output_type=None,
            )
        except Exception as exc:
            logger.exception("Model prediction failed")
            response_errors = getattr(exc, "response_error", None)
            return ModelOutput(
                usage={},
                model=self.name or "",
                output="",
                scored_output="",
                thoughts=None,
                raw_output=getattr(exc, "output", None),
                error=str(response_errors) if response_errors else None,
                exception=_exception_transformer(sys.exc_info()),  # pyright: ignore[reportArgumentType]
            )

        # Flatten all the usage and remove zeros
        usage: dict[str, int] = {}
        for token_type, token_count in asdict(model_output.usage).items():
            if isinstance(token_count, dict):
                usage.update(token_count)
            else:
                usage[token_type] = token_count
        usage = {token: count for token, count in usage.items() if count > 0}

        prediction = ModelOutput(
            usage=usage,
            model=self.name or "",
            output=self._output_serializer(model_output.output),
            scored_output="",
            thoughts=model_output.thoughts,
            raw_output=model_output.raw_output,
            error=str(model_output.ai_response_error) if model_output.ai_response_error else None,
            exception=None,
        )
        prediction["scored_output"] = self._scored_output_func(dict(prediction))
        return prediction

    def predict(self, index: int, model_input: Any, *args: Any, **kwargs: Any) -> ModelOutput:  # noqa: ARG002
        """Fetch the model answer from the json."""
        prediction_path = self._output_dir.joinpath(f"prediction_{index}.json")

        return from_json(prediction_path.read_bytes())
