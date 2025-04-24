from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

import logfire
import structlog
from fastapi import APIRouter, Depends, FastAPI, Request

from gptnt.api.experiment_manager import ExperimentManager
from gptnt.api.player_client import SupervisedPlayerClient
from gptnt.api.room_client import SupervisedRoomManagerClient
from gptnt.api.structures import PlayerMetadata, RoomMetadata

logger = structlog.get_logger()

router = APIRouter()


async def _get_supervised_players(request: Request) -> list[SupervisedPlayerClient]:
    """Get the supervised players from the state of the app."""
    return request.app.state.manager.players


async def _get_supervised_rooms(request: Request) -> list[SupervisedRoomManagerClient]:
    """Get the supervised players from the state of the app."""
    return request.app.state.manager.rooms


SupervisedPlayersDep = Annotated[list[SupervisedPlayerClient], Depends(_get_supervised_players)]
SupervisedRoomsDep = Annotated[list[SupervisedRoomManagerClient], Depends(_get_supervised_rooms)]


@router.get("/health")
def health() -> bool:
    """Check if the experiment manager is healthy."""
    return True


@logfire.instrument("Connect player")
@router.post("/connect-player")
async def connect_player(
    player_metadata: PlayerMetadata, supervised_players: SupervisedPlayersDep
) -> None:
    """Connects a new player to the experiment manager."""
    supervised_players.append(SupervisedPlayerClient.from_metadata(player_metadata))


@logfire.instrument("Connect room")
@router.post("/connect-room")
async def connect_room(room_metadata: RoomMetadata, supervised_rooms: SupervisedRoomsDep) -> None:
    """Connects a new room manager to the experiment manager."""
    supervised_rooms.append(SupervisedRoomManagerClient.from_metadata(room_metadata))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Lifespan to run the room manager API."""
    # Create the manager
    manager = ExperimentManager()

    logger.info("Starting ExperimentManager")
    # Start the manager and store it in the app
    async with manager:
        app.state.manager = manager
        yield

    logger.info("Shutting down ExperimentManager")
