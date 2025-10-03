from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from gptnt.experiments.experiments import ExperimentSpec
from gptnt.services.experiment_manager.experiment_manager import ExperimentManager

logger = structlog.get_logger()
router = APIRouter()


def _get_experiment_manager(request: Request) -> ExperimentManager:
    """Get the ExperimentManager instance from the request state."""
    return request.app.state.experiment_manager


ExperimentManagerDep = Annotated[ExperimentManager, Depends(_get_experiment_manager)]


class Specs(BaseModel):
    """Model for experiment specifications."""

    specs: list[ExperimentSpec]


@router.get("/health")
async def health() -> bool:
    """Check if the experiment manager is healthy."""
    return True


@router.post("/add-specs")
async def add_experiment_specs(specs: Specs, experiment_manager: ExperimentManagerDep) -> None:
    """Add new experiment specifications."""
    logger.info("Adding new experiment specs", total_specs=len(specs.specs))
    experiment_manager.specs.update(specs.specs)
    logger.info("Experiment specs added", total_specs=len(experiment_manager.specs))
