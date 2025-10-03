import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import Depends, FastAPI, Request
from redis import Redis

from gptnt.ktane.client import KtaneClient
from gptnt.services.game.process_manager import GameProcessManager
from gptnt.services.game.state_monitor import GameStateMonitor
from gptnt.services.game.supervisor import GameSupervisor

logger = structlog.get_logger()


@asynccontextmanager
async def game_lifespan(app: FastAPI, *, url: str, redis: Redis) -> AsyncGenerator[None]:
    """Lifespan context manager for the app."""
    service_uuid = uuid.uuid4()

    logger.warning("Starting game service", service_uuid=str(service_uuid))
    game_supervisor = GameSupervisor(url=url, redis=redis, uuid=service_uuid)

    async with game_supervisor.lifespan():
        app.state.service_uuid = service_uuid
        app.state.game_supervisor = game_supervisor
        app.state.ktane_client = game_supervisor.ktane_client
        app.state.state_monitor = game_supervisor.state_monitor
        app.state.process_manager = game_supervisor.process_manager
        yield

    logger.info("Game service shut down complete.")


async def get_game_supervisor(request: Request) -> GameSupervisor:
    """Dependency to get the GameSupervisor from the app state."""
    return request.app.state.game_supervisor


async def get_ktane_client(request: Request) -> KtaneClient:
    """Dependency to get the KtaneClient from the app state."""
    return request.app.state.game_supervisor.ktane_client


async def get_game_state_monitor(request: Request) -> GameStateMonitor:
    """Dependency to get the GameStateMonitor from the app state."""
    return request.app.state.game_supervisor.state_monitor


async def get_game_process_manager(request: Request) -> GameProcessManager:
    """Dependency to get the GameProcessManager from the app state."""
    return request.app.state.game_supervisor.process_manager


GameSupervisorDep = Annotated[GameSupervisor, Depends(get_game_supervisor)]
KtaneClientDep = Annotated[KtaneClient, Depends(get_ktane_client)]
GameStateMonitorDep = Annotated[GameStateMonitor, Depends(get_game_state_monitor)]
GameProcessManagerDep = Annotated[GameProcessManager, Depends(get_game_process_manager)]
