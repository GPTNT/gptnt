from unittest.mock import MagicMock
from uuid import uuid4

import anyio
import fakeredis
import pytest
from faststream.redis import TestRedisBroker

from gptnt.common.paths import Paths
from gptnt.ktane.state.game import GameState
from gptnt.services.broker import create_redis_broker
from gptnt.services.experiment_manager.experiment_manager import ExperimentManager
from gptnt.services.game.service import GameService
from gptnt.services.heartbeat.base import PlayerState
from gptnt.services.player.service import PlayerService

paths = Paths()


@pytest.mark.anyio
async def test_player_service_starts_and_responds_to_get_state() -> None:
    """Test that the player service starts and responds to get_state RPC."""
    # Create broker with TestRedisBroker
    broker = create_redis_broker("redis://fake", client_name="test")
    fake_redis = fakeredis.FakeRedis(decode_responses=True)

    # Create player controller with mocked dependencies
    player_service = PlayerService(
        uuid="test-player",
        redis=fake_redis,
        broker=broker,
        nobf_generator=MagicMock(),
        capabilities=MagicMock(),
        observation_handler=MagicMock(),
        action_predictor=MagicMock(),
        experiment_recorder=MagicMock(),
        game_client=MagicMock(),
        incoming_message_handler=MagicMock(),
    )

    async with TestRedisBroker(broker) as br:
        # Call get_state via RPC
        _ = await br.publish({}, "player:test-player:commands:get_state")
        # Player should be in idle state
        assert player_service.state == PlayerState.idle


@pytest.mark.anyio
async def test_game_service_starts_and_responds_to_get_game_state() -> None:
    """Test that the game service starts and responds to get_game_state RPC."""
    # Create broker with TestRedisBroker
    broker = create_redis_broker("redis://fake", client_name="test")
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    game_uuid = uuid4()

    # Create game service with mocked dependencies
    game_service = GameService(redis=fake_redis, broker=broker, uuid=game_uuid)

    async with TestRedisBroker(broker) as br:
        # Call get_game_state via RPC - just verify it doesn't crash
        _ = await br.publish({}, f"game:{game_uuid}:commands:get_game_state")
        # Game service exists and has a state monitor
        assert game_service.state_monitor is not None
        assert game_service.state_monitor.state.value in GameState


@pytest.mark.anyio
async def test_player_service_tells_em_its_ready(
    experiment_manager: ExperimentManager, player_service: PlayerService
) -> None:
    """Test that the player service can connect to the EM."""
    await anyio.sleep(5)

    for player in experiment_manager.ready_players:
        if player.uuid == player_service.uuid:
            break
    else:
        pytest.fail("Player controller UUID not found in EM ready players")


@pytest.mark.anyio
async def test_game_service_tells_em_its_ready(
    experiment_manager: ExperimentManager, game_service: GameService
) -> None:
    """Test that the game service can connect to the EM."""
    for game in experiment_manager.ready_games:
        if game.uuid == game_service.uuid:
            break
    else:
        pytest.fail("Game service UUID not found in EM ready games")


@pytest.mark.anyio
async def test_multiple_services_connect_to_em(
    experiment_manager: ExperimentManager, game_service: GameService, player_service: PlayerService
) -> None:
    """Test that the EM can connect to the game and player services."""
    for game in experiment_manager.ready_games:
        if game.uuid == game_service.uuid:
            break
    else:
        pytest.fail("Game service UUID not found in EM ready games")

    for player in experiment_manager.ready_players:
        if player.uuid == player_service.uuid:
            break
    else:
        pytest.fail("Player service UUID not found in EM ready players")
