import anyio
import pytest
from httpx import AsyncClient

from gptnt.common.paths import Paths
from gptnt.services.experiment_manager.experiment_manager import ExperimentManager
from gptnt.services.game.supervisor import GameSupervisor
from gptnt.services.player.supervisor import PlayerSupervisor

paths = Paths()


@pytest.mark.anyio
async def test_player_service_starts_and_is_available(player_app_client: AsyncClient) -> None:
    """Test that the player service starts and is available."""
    health_response = await player_app_client.get("/health")
    assert health_response.status_code == 200

    state_response = await player_app_client.get("/state")
    assert state_response.status_code == 200
    assert state_response.json() == 0, "Player service is not in idle state"


@pytest.mark.anyio
async def test_game_service_starts_and_is_available(game_app_client: AsyncClient) -> None:
    """Test that the game service starts and is available."""
    health_response = await game_app_client.get("/health")
    assert health_response.status_code == 200

    state_response = await game_app_client.get("/state")
    assert state_response.status_code == 200
    assert state_response.json() == "Setup"


@pytest.mark.anyio
async def test_player_service_tells_em_its_ready(
    experiment_manager: ExperimentManager, player_supervisor: PlayerSupervisor
) -> None:
    """Test that the player service can connect to the EM."""
    await anyio.sleep(5)

    for player in experiment_manager.ready_players:
        if player.uuid == player_supervisor.uuid:
            break
    else:
        pytest.fail("Player supervisor UUID not found in EM ready players")


@pytest.mark.anyio
async def test_game_service_tells_em_its_ready(
    experiment_manager: ExperimentManager, game_supervisor: GameSupervisor
) -> None:
    """Test that the game service can connect to the EM."""
    await anyio.sleep(5)

    for game in experiment_manager.ready_games:
        if game.uuid == game_supervisor.uuid:
            break
    else:
        pytest.fail("Game supervisor UUID not found in EM ready games")


@pytest.mark.anyio
async def test_multiple_services_connect_to_em(
    experiment_manager: ExperimentManager,
    game_supervisor: GameSupervisor,
    player_supervisor: PlayerSupervisor,
) -> None:
    """Test that the EM can connect to the game and player services."""
    await anyio.sleep(10)

    for game in experiment_manager.ready_games:
        if game.uuid == game_supervisor.uuid:
            break
    else:
        pytest.fail("Game supervisor UUID not found in EM ready games")

    for player in experiment_manager.ready_players:
        if player.uuid == player_supervisor.uuid:
            break
    else:
        pytest.fail("Player supervisor UUID not found in EM ready players")
