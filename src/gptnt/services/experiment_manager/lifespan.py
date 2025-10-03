from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from gptnt.services.experiment_manager.experiment_manager import ExperimentManager

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI, *, experiment_manager: ExperimentManager) -> AsyncIterator[None]:
    """Lifespan for the experiment manager application."""
    async with experiment_manager.lifespan():
        app.state.experiment_manager = experiment_manager
        yield
    logger.info("Experiment manager application shutting down")
