import asyncio
from contextlib import suppress
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from httpx import AsyncClient

from gptnt.api.structures import GameMetadata, RoomMetadata
from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.players.ai.ai_player import AIPlayer
from gptnt.players.ai.defuser import BaseDefuserPlayer
from gptnt.players.base_player import BasePlayer
from gptnt.players.human.controller import Controller
from gptnt.players.human.views.defuser import DefuserPlayerView

logger = structlog.get_logger()

player_router = APIRouter()


async def _get_player(request: Request) -> BasePlayer:
    return request.app.state.player


PlayerDep = Annotated[BasePlayer, Depends(_get_player)]


@player_router.get("/health")
async def health() -> bool:
    """Get the health of the API."""
    return True


@player_router.post("/join-room")
async def join_room(room: RoomMetadata, player: PlayerDep) -> None:
    """Join a room and connect to its dialogue space."""
    with suppress(AttributeError):
        logger.debug("Disconnecting from previous room")
        await player.disconnect_from_room()

    # Reset dialogue-space client
    player.dialogue_space_client = DialogueSpaceClient.from_url(room.dialogue_space_url)
    player.tracker.reset()

    # TODO: Fix the Ktane player hackery
    if isinstance(player, Controller) and isinstance(player.view, DefuserPlayerView):
        player.view.ktane_client.update_client(AsyncClient(base_url=room.ktane_url))
    if isinstance(player, BaseDefuserPlayer):
        player.game_client.update_client(AsyncClient(base_url=room.ktane_url))

    await player.connect()


@player_router.post("/start-experiment")
async def start_experiment(player: PlayerDep, game_metadata: GameMetadata) -> bool:
    """Start the experiment."""
    player.tracker.on_game_start(
        experiment_spec=game_metadata.experiment_spec,
        game_id=game_metadata.game_id,
        role=game_metadata.player_metadata.player_role,
        player_id=player.metadata.uuid,
        additional_metadata={},
    )
    return True


@player_router.post("/run-for-game")
async def run_for_game(player: PlayerDep, request: Request) -> None:
    """Run the game in 'parallel' mode."""
    if player.metadata.player_type == "ai":
        request.app.state.main_loop_task = asyncio.create_task(player.run_parallel())


@player_router.post("/run-for-turn")
async def run_for_turn(player: PlayerDep, request: Request) -> None:
    """Perform one step in the game.

    Only makes sense for AI players.
    """
    if player.metadata.player_type == "ai":
        request.app.state.main_loop_task = asyncio.create_task(player.run_sequential())
        await request.app.state.main_loop_task


@player_router.post("/stop-experiment")
async def stop_experiment(player: PlayerDep, request: Request) -> None:
    """Stop the experiment and disconnect from the room."""
    # Stop AI from taking any more actions
    loop_task = getattr(request.app.state, "main_loop_task", None)
    if player.metadata.player_type == "ai" and loop_task:
        loop_task.cancel()

    if isinstance(player, AIPlayer):
        await player.on_experiment_stop()

    # Disconnect from the room
    await player.disconnect_from_room()
    logger.info("Stopped experiment for player")
