from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated

import logfire
import structlog
from fastapi import APIRouter, Depends, FastAPI, Request
from pydantic import BaseModel

from gptnt.core.experiments.experiments import ExperimentSpec
from gptnt.interactive.services.experiment_manager.experiment_manager import ExperimentManager

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = structlog.get_logger()
router = APIRouter()


@asynccontextmanager
async def lifespan(app: FastAPI, *, experiment_manager: ExperimentManager) -> AsyncIterator[None]:
    """Lifespan for the experiment manager application."""
    async with experiment_manager.lifespan():
        app.state.experiment_manager = experiment_manager
        yield
    logger.info("Flushing logfire spans")
    _ = logfire.shutdown()

    logger.info("Experiment manager application shutting down")


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
