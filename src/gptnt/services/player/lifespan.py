from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import Depends, FastAPI, Request

from gptnt.players.observation_handler import ObservationHandler
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.services.events.heartbeat import ReadyState
from gptnt.services.game.client import GameClient
from gptnt.services.player.message_handler import MessageManager
from gptnt.services.player.supervisor import PlayerSupervisor

logger = structlog.get_logger()


@asynccontextmanager
async def player_lifespan(
    app: FastAPI, *, player_supervisor: PlayerSupervisor
) -> AsyncGenerator[None]:
    """Lifespan context manager for the player service."""
    supervisor = player_supervisor

    async with supervisor.lifespan():
        app.state.supervisor = supervisor
        app.state.supervisor.ready_state = ReadyState.ready
        yield

    logger.info("Player service shut down complete.")


async def get_message_manager(request: Request) -> MessageManager:
    """Dependency to get the MessageManager from the app state."""
    return request.app.state.supervisor.message_manager


async def get_observation_handler(request: Request) -> ObservationHandler:
    """Dependency to get the ObservationHandler from the app state."""
    return request.app.state.supervisor.observation_handler


async def get_capabilities(request: Request) -> PlayerCapabilities:
    """Dependency to get the PlayerCapabilities from the app state."""
    return request.app.state.supervisor.capabilities


async def get_player_service_state(request: Request) -> PlayerSupervisor:
    """Dependency to get the PlayerServiceState from the app state."""
    return request.app.state.supervisor


async def get_game_client(request: Request) -> GameClient:
    """Dependency to get the GameClient from the app state."""
    return request.app.state.supervisor.game_client


async def get_player_protocol(request: Request) -> PlayerProtocol:
    """Dependency to get the PlayerProtocol from the app state."""
    return request.app.state.supervisor.protocol


MessageManagerDep = Annotated[MessageManager, Depends(get_message_manager)]
ObservationHandlerDep = Annotated[ObservationHandler, Depends(get_observation_handler)]
CapabilitiesDep = Annotated[PlayerCapabilities, Depends(get_capabilities)]
PlayerSupervisorDep = Annotated[PlayerSupervisor, Depends(get_player_service_state)]
GameClientDep = Annotated[GameClient, Depends(get_game_client)]
PlayerProtocolDep = Annotated[PlayerProtocol, Depends(get_player_protocol)]
