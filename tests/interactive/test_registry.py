"""Unit tests for the service registry's ready-player / ready-game filters (no Redis)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

from gptnt.interactive.services.heartbeat.base import PlayerState, ReadyState
from gptnt.interactive.services.heartbeat.game import GameHeartbeat
from gptnt.interactive.services.heartbeat.player import PlayerHeartbeat
from gptnt.interactive.services.registry.manifest import ServiceManifest, ServiceState
from gptnt.interactive.services.registry.registry import ServiceRegistry
from gptnt.ktane.state.game import GameState
from gptnt.players.specification import PlayerCapabilities


def player_manifest(
    *, ready: bool = True, state: PlayerState = PlayerState.idle
) -> ServiceManifest[PlayerHeartbeat]:
    heartbeat = PlayerHeartbeat(
        uuid=uuid4(),
        service_name="player",
        ready_state=ReadyState.ready if ready else ReadyState.not_ready,
        capabilities=PlayerCapabilities(player_name="test-player", player_type="ai"),
        state=state,
    )
    return ServiceManifest(heartbeat=heartbeat)


def game_manifest(
    *, ready: bool = True, state: GameState = GameState.main_menu
) -> ServiceManifest[GameHeartbeat]:
    heartbeat = GameHeartbeat(
        uuid=uuid4(),
        service_name="game",
        ready_state=ReadyState.ready if ready else ReadyState.not_ready,
        state=state,
        ktane_url="http://localhost:1",
    )
    return ServiceManifest(heartbeat=heartbeat)


def make_registry(*manifests: ServiceManifest[Any]) -> ServiceRegistry:
    registry = ServiceRegistry(redis=MagicMock())
    for manifest in manifests:
        registry.connected_services[manifest.uuid] = manifest
    return registry


def test_ready_players_requires_ready_and_idle() -> None:
    idle = player_manifest()
    mid_turn = player_manifest(state=PlayerState.waiting_for_turn)
    not_ready = player_manifest(ready=False)

    registry = make_registry(idle, mid_turn, not_ready)

    assert registry.ready_players == [idle]


def test_player_in_experiment_is_not_ready() -> None:
    player = player_manifest()
    player.state = ServiceState.in_experiment  # the EM-level state, set on matchmaking

    registry = make_registry(player)

    assert registry.ready_players == []


def test_ready_games_requires_main_menu() -> None:
    at_menu = game_manifest()
    running = game_manifest(state=GameState.lights_on)

    registry = make_registry(at_menu, running)

    assert registry.ready_games == [at_menu]


def test_players_and_games_do_not_cross_contaminate() -> None:
    player = player_manifest()
    game = game_manifest()

    registry = make_registry(player, game)

    assert registry.ready_players == [player]
    assert registry.ready_games == [game]
