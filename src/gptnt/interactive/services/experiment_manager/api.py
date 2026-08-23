from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated

import logfire
import structlog
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from gptnt.experiments.spec import ExperimentSpec
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


class ActiveExperiments(BaseModel):
    """The attempt names the EM is currently working on."""

    running: list[str]
    queued: list[str]


@router.get("/health")
async def health() -> bool:
    """Check if the experiment manager is healthy."""
    return True


@router.post("/add-specs")
async def add_experiment_specs(specs: Specs, experiment_manager: ExperimentManagerDep) -> None:
    """Add new attempts and reject a name already bound to different inputs."""
    logger.info("Adding new experiment specs", total_specs=len(specs.specs))
    known_attempts = {spec.attempt_name: spec for spec in experiment_manager.specs}
    known_attempts.update(
        (session.spec.attempt_name, session.spec) for session in experiment_manager.sessions
    )
    new_specs = []
    for spec in specs.specs:
        existing = known_attempts.get(spec.attempt_name)
        if existing is None:
            known_attempts[spec.attempt_name] = spec
            new_specs.append(spec)
        elif existing != spec:
            raise HTTPException(
                status_code=409,
                detail=f"Experiment attempt {spec.attempt_name!r} has conflicting specifications.",
            )

    experiment_manager.specs.extend(new_specs)
    logger.info("Experiment specs added", total_specs=len(experiment_manager.specs))


@router.get("/active")
async def active_experiments(experiment_manager: ExperimentManagerDep) -> ActiveExperiments:
    """Return the attempt names in flight: running sessions plus queued-but-unmatched specs.

    `status` overlays these onto the on-disk completion view so a benchmark run shows live progress
    without W&B.
    """
    return ActiveExperiments(
        running=[session.spec.attempt_name for session in experiment_manager.sessions],
        queued=[spec.attempt_name for spec in experiment_manager.specs],
    )
