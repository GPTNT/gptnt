import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

import logfire
import structlog
from fastapi import APIRouter, Depends, FastAPI, Request

from gptnt.api.experiment_manager import ExperimentManager
from gptnt.api.player_client import SupervisedPlayerClient
from gptnt.api.room_client import SupervisedRoomManagerClient
from gptnt.api.structures import RoomMetadata
from gptnt.common.paths import Paths
from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.players.base_player import PlayerMetadata

logger = structlog.get_logger()

router = APIRouter()

paths = Paths()


async def _get_experiments(request: Request) -> list[SupervisedPlayerClient]:
    """Get the experiments from the state of the app."""
    return request.app.state.manager.experiments


async def _get_supervised_players(request: Request) -> list[SupervisedPlayerClient]:
    """Get the supervised players from the state of the app."""
    return request.app.state.manager.players


async def _get_supervised_rooms(request: Request) -> list[SupervisedRoomManagerClient]:
    """Get the supervised players from the state of the app."""
    return request.app.state.manager.rooms


ExperimentSpecDep = Annotated[set[ExperimentSpec], Depends(_get_experiments)]
SupervisedPlayersDep = Annotated[list[SupervisedPlayerClient], Depends(_get_supervised_players)]
SupervisedRoomsDep = Annotated[list[SupervisedRoomManagerClient], Depends(_get_supervised_rooms)]


@router.get("/health")
def health() -> bool:
    """Check if the experiment manager is healthy."""
    return True


@logfire.instrument("Add Experiment")
@router.post("/add-experiment")
async def add_experiment(experiment_spec: ExperimentSpec, experiments: ExperimentSpecDep) -> None:
    """Connects a new player to the experiment manager."""
    experiments.add(experiment_spec)


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
    app.state.manager = manager

    # Add all experiments genrated using `src/gptnt/exntrypoints/generate_experiments.py`
    experiments = {
        ExperimentSpec.model_validate_json(path.read_text())
        for path in paths.experiments.rglob("*.json")
    }
    assert len(experiments) > 0, (
        "No experiments found, please generate some using `uv run ./src/gptnt/exntrypoints/generate_experiments.py`"
    )
    logger.info(f"Starting ExperimentManager with {len(experiments)} experiments.")
    manager.experiments = experiments

    manager.tasks.append(asyncio.create_task(manager.main_loop()))
    yield

    logger.info("Shutting down ExperimentManager")
    manager.should_exit = True
    for task in manager.tasks:
        _ = task.cancel()
