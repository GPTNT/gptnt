import json
from functools import lru_cache
from typing import Any, NamedTuple

import structlog

from gptnt.common.paths import Paths

_logger = structlog.get_logger()
paths = Paths()


class ModelTokenCost(NamedTuple):
    """Token cost per model."""

    model: str
    input_token_cost: float
    output_token_cost: float


@lru_cache(maxsize=1)
def load_cost_json() -> dict[str, dict[str, Any]]:
    """Load the token cost JSON file."""
    loaded_json = paths.storage.joinpath("llm_cost.json").read_bytes()
    loaded_json_as_dict: dict[str, dict[str, Any]] = json.loads(loaded_json)
    return loaded_json_as_dict


@lru_cache(maxsize=1)
def load_model_token_cost(*, model_name: str) -> ModelTokenCost:
    """Load the token cost JSON file."""
    loaded_json_as_dict = load_cost_json()

    model_costs = loaded_json_as_dict.get(model_name)
    if model_costs is None:
        _logger.warning(f"Model {model_name} not found in cost JSON file. Defaulting to 0 cost.")
        return ModelTokenCost(model=model_name, input_token_cost=0, output_token_cost=0)

    return ModelTokenCost(
        model=model_name,
        input_token_cost=model_costs["input_cost_per_token"],
        output_token_cost=model_costs["output_cost_per_token"],
    )
