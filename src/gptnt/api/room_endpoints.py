from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request

from gptnt.api.room_manager import RoomManager
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.game import GameState

_logger = structlog.get_logger()

router = APIRouter()


async def _get_room_manager(request: Request) -> RoomManager:
    return request.app.state.manager


RoomManagerDep = Annotated[RoomManager, Depends(_get_room_manager)]


@router.get("/health")
async def health(room_manager: RoomManagerDep) -> str:
    """Health check endpoint."""
    return room_manager.lifecycle_stage.value


@router.post("/reset-room")
async def reset_room(room_manager: RoomManagerDep) -> None:
    """Reset the room."""
    if not room_manager.reset_raised.is_set():
        _logger.info("Resetting room")
        room_manager.reset_raised.set()


@router.post("/configure-experiment")
async def configure_experiment(config: KtaneMissionSpec, room_manager: RoomManagerDep) -> None:
    """Configure the experiment."""
    _logger.info("Configuring experiment", config=config)
    if not await room_manager.ktane_client.start_mission(specification=config):
        raise HTTPException(status_code=500, detail="Game not ready for new mission")  # noqa: WPS432


@router.post("/start-experiment")
async def start_experiment(room_manager: RoomManagerDep) -> None:
    """Start the experiment."""
    if room_manager.game_state is not GameState.lights_off:
        raise HTTPException(status_code=500, detail="Room not ready")  # noqa: WPS432

    if not await room_manager.ktane_client.resume_time():
        # Reaching this implies an error with the room.
        # This will be caught by a supervisor, and the room will be restarted
        raise HTTPException(status_code=500, detail="Room dead")  # noqa: WPS432


@asynccontextmanager
async def lifespan(app: FastAPI, *, api_host: str, api_port: int) -> AsyncGenerator[None]:
    """Lifespan to run the room manager API."""
    # Create the manager
    manager = RoomManager(hostname=api_host, port=api_port)

    # Start the manager and store it in the app
    async with manager:
        app.state.manager = manager
        yield

    # Make sure to kill the game otherwise we have zombies
    manager.kill_game_process()
