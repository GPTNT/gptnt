import asyncio
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request
from httpx import AsyncClient

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.experiments.structures import RoomManagerAPIInfo
from gptnt.ktane.client import KtaneClient
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
async def join_room(room: RoomManagerAPIInfo, player: PlayerDep) -> None:
    """Join a room and connect to its dialogue space."""
    # logger.debug("Disconnecting from previous room")
    # await player.disconnect_from_room()

    # Reset dialogue-space client
    player.dialogue_space_client = DialogueSpaceClient.from_url(room.dialogue_space_url)

    # TODO: Fix the Ktane player hackery
    if isinstance(player, Controller) and isinstance(player.view, DefuserPlayerView):
        player.view.ktane_client = KtaneClient(client=AsyncClient(base_url=room.ktane_url))
    if isinstance(player, BaseDefuserPlayer):
        player.game_client = KtaneClient(client=AsyncClient(base_url=room.ktane_url))

    await player.connect()


@player_router.post("/start-experiment")
async def start_experiment() -> bool:
    """Start the experiment."""
    # TODO: Add W&B stuff
    return True


@player_router.post("/run-for-game")
async def run_for_game(player: PlayerDep, request: Request) -> None:
    """Run the game in 'parallel' mode."""
    if player.player_type == "ai":
        request.app.state.main_loop_task = asyncio.create_task(player.run())


@player_router.post("/run-for-turn")
async def run_for_turn(player: PlayerDep) -> None:
    """Perform one step in the game.

    Only makes sense for AI players.
    """
    if player.player_type == "ai":
        await player.run_once()


@player_router.post("/stop-experiment")
async def stop_experiment(player: PlayerDep, request: Request) -> None:
    """Stop the experiment and disconnect from the room."""
    # Stop AI from taking any more actions
    loop_task = getattr(request.app.state, "main_loop_task", None)
    if player.player_type == "ai" and loop_task:
        loop_task.cancel()

    # Disconnect from the room
    await player.disconnect_from_room()

    # TODO: Add W&B stuff
