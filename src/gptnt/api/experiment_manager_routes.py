import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, FastAPI, Request

from gptnt.api.experiment_manager import ExperimentManager
from gptnt.api.player_client import SupervisedPlayerClient
from gptnt.api.room_client import SupervisedRoomManagerClient
from gptnt.api.structures import RoomMetadata
from gptnt.common.paths import Paths
from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.players.metrics.wandb import check_if_experiments_on_wandb
from gptnt.players.structures import PlayerMetadata

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


async def _get_manager_tasks(request: Request) -> list[asyncio.Task[None]]:
    """Get the running tasks from the state of the app."""
    return request.app.state.manager.tasks


ExperimentSpecDep = Annotated[set[ExperimentSpec], Depends(_get_experiments)]
SupervisedPlayersDep = Annotated[list[SupervisedPlayerClient], Depends(_get_supervised_players)]
SupervisedRoomsDep = Annotated[list[SupervisedRoomManagerClient], Depends(_get_supervised_rooms)]
ManagerTasksDep = Annotated[list[asyncio.Task[None]], Depends(_get_manager_tasks)]


@router.get("/health")
def health() -> bool:
    """Check if the experiment manager is healthy."""
    return True


@router.post("/add-experiment")
async def add_experiment(experiment_spec: ExperimentSpec, experiments: ExperimentSpecDep) -> None:
    """Connects a new player to the experiment manager."""
    experiments.add(experiment_spec)
    logger.info(
        f"Added experiment {experiment_spec.experiment_name}; currently {len(experiments)} experiments."
    )


@router.post("/connect-player")
async def connect_player(
    player_metadata: PlayerMetadata,
    supervised_players: SupervisedPlayersDep,
    tasks: ManagerTasksDep,
) -> None:
    """Connects a new player to the experiment manager and starts its supervisors."""
    new_player = SupervisedPlayerClient.from_metadata(player_metadata)
    await new_player.start()
    tasks.append(asyncio.create_task(coro=new_player.supervisor_loop()))
    supervised_players.append(new_player)
    logger.info(
        f"Connected player {player_metadata.player_name} ({player_metadata.player_type}; {player_metadata.player_role}) to the experiment manager."
    )


@router.post("/connect-room")
async def connect_room(
    room_metadata: RoomMetadata, supervised_rooms: SupervisedRoomsDep, tasks: ManagerTasksDep
) -> None:
    """Connects a new room manager to the experiment manager."""
    # TODO: Stop the RoomManager from re-connecting after a restart, this is a HACK
    old_rooms = [room for room in supervised_rooms if room.metadata.uuid == room_metadata.uuid]
    if len(old_rooms) > 1:
        raise ValueError("There should be at most one room with the same UUID.")

    if old_rooms:
        logger.warning(
            f"Room {room_metadata.uuid} already connected to the experiment manager. Updating metadata for room."
        )
        old_rooms[0].metadata = room_metadata
        return

    new_room = SupervisedRoomManagerClient.from_metadata(room_metadata)
    await new_room.start()
    tasks.append(asyncio.create_task(coro=new_room.supervisor_loop()))
    supervised_rooms.append(new_room)
    logger.info(
        f"Connected room {room_metadata.uuid} ({room_metadata.fastapi_url}) to the experiment manager."
    )


@asynccontextmanager
async def lifespan(app: FastAPI, *, filter_with_wandb: bool = False) -> AsyncGenerator[None]:
    """Lifespan to run the room manager API."""
    # Create the manager
    manager = ExperimentManager()
    app.state.manager = manager

    # Add all experiments generated using `src/gptnt/exntrypoints/generate_experiments.py`
    experiments = {
        ExperimentSpec.model_validate_json(path.read_text())
        for path in paths.experiments.rglob("*.json")
    }
    if not experiments:
        logger.warning(
            "No experiments found. Generate some with `uv run ./src/gptnt/entrypoints/generate_experiments.py` and restart; OR use the entrypoint to provide them."
        )
    test_experiments = {
        ExperimentSpec.model_validate_json(path.read_text())
        for path in paths.test_experiments.rglob("*.json")
    }
    experiments = experiments | test_experiments  # noqa: WPS350 (Huh? What is this?)

    # Flag to decide if experiments already on wandb should be filtered out
    if filter_with_wandb:
        experiments = check_if_experiments_on_wandb(
            experiments=experiments,
            wandb_entity=os.getenv("WANDB_ENTITY", "gptnt"),
            wandb_project=os.getenv("WANDB_PROJECT", "gptnt"),
        )

    logger.info(f"Starting ExperimentManager with {len(experiments)} experiments.")

    manager.experiments = experiments

    manager.tasks.append(asyncio.create_task(manager.main_loop()))
    yield

    logger.info("Shutting down ExperimentManager")
    manager.should_exit = True
    for task in manager.tasks:
        _ = task.cancel()
