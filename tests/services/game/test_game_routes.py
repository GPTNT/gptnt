# import json
# from collections.abc import AsyncGenerator

# import httpx
# import pytest
# import pytest_asyncio
# import respx
# from fastapi import FastAPI
# from pytest_mock import MockerFixture

# from gptnt.ktane.state.game import GameState
# from gptnt.services.game.client import GameClient
# from gptnt.services.game.routes import router
# from gptnt.services.game.state_monitor import GameStateMonitor


# @pytest_asyncio.fixture()
# async def game_client(
#     mocker: MockerFixture, state_monitor: GameStateMonitor
# ) -> AsyncGenerator[GameClient]:
#     """Create a test client that can be used to make request to the game API."""
#     app = FastAPI()
#     app.include_router(router)
#     app.state.game_supervisor = mocker.Mock()
#     app.state.game_supervisor.state_monitor = state_monitor
#     async with httpx.AsyncClient(
#         transport=httpx.ASGITransport(app=app), base_url="http://test"
#     ) as client:
#         game_client = GameClient()
#         game_client._client = client
#         yield game_client


# @pytest.mark.asyncio
# async def test_can_get_health(game_client: GameClient) -> None:
#     response = await game_client.healthcheck()
#     assert response is True, "Health check should return True"


# @pytest.mark.asyncio
# @respx.mock
# @pytest.mark.parametrize("game_state", list(GameState))
# async def test_can_get_game_state(
#     game_client: GameClient, base_url: str, game_state: GameState
# ) -> None:
#     """Test getting the game state."""
#     _ = respx.get(f"{base_url}/state").mock(
#         return_value=httpx.Response(202, json=json.dumps(game_state.value))
#     )
#     response = await game_client.get_game_state()
#     assert isinstance(response, GameState)
#     assert response == game_state, "Game state should match the mocked state"
