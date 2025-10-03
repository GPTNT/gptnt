import os
from collections.abc import AsyncGenerator, Generator

import pytest
import respx
from anyio.pytest_plugin import FreePortFactory
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, MockTransport
from pydantic import RedisDsn
from pytest_cases import fixture, param_fixture, parametrize
from respx.transports import TryTransport

from gptnt.common.async_ops import periodic
from gptnt.common.paths import Paths
from gptnt.common.respx_router import AutoPassThroughRouter
from gptnt.entrypoints.run_experiment_manager import run as run_experiment_manager
from gptnt.entrypoints.run_game_instance import run as run_game_instance
from gptnt.entrypoints.run_player import run as run_player
from gptnt.experiments.experiments import ExperimentSpec
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.players.specification import PlayerProtocol
from gptnt.services.experiment_manager.experiment_manager import ExperimentManager
from gptnt.services.game.supervisor import GameSupervisor
from gptnt.services.player.supervisor import PlayerSupervisor

paths = Paths()

pytestmark = pytest.mark.anyio


@fixture(autouse=True)
async def respx_mock(respx_mock: respx.MockRouter) -> AsyncGenerator[AutoPassThroughRouter]:
    yield AutoPassThroughRouter.from_mock_router(respx_mock)


@fixture(autouse=True, scope="session")
def setup_env_vars() -> None:
    """Fixture to set up environment variables for the tests."""
    os.environ["TESTING"] = "1"


# @fixture
# def anyio_backend() -> str:
#     return "trio"


@fixture
def redis_server_dsn() -> Generator[RedisDsn]:
    """Fixture to run a Redis server for the duration of the tests."""
    # port = free_tcp_port_factory()
    # server_address = ("127.0.0.1", port)
    # server = TcpFakeServer(server_address, server_type="redis")
    # thread = Thread(target=server.serve_forever, daemon=False)
    # thread.start()
    try:
        yield RedisDsn("redis://localhost:6379")
    finally:
        # server.shutdown()
        # server.server_close()
        # thread.join(timeout=5)
        pass  # noqa: WPS420


player_role = param_fixture("player_role", ["test_expert", "test_defuser"])


@fixture
async def player_app(
    free_tcp_port_factory: FreePortFactory, redis_server_dsn: RedisDsn, player_role: str
) -> AsyncGenerator[FastAPI]:
    """Fixture to create a Player app instance."""
    port = free_tcp_port_factory()
    app = run_player(
        port=port, redis_dsn=redis_server_dsn, hydra_overrides=[f"model={player_role}"]
    )
    async with LifespanManager(app):
        yield app


@fixture
async def player_app_client(
    player_app: FastAPI, respx_mock: respx.MockRouter
) -> AsyncGenerator[AsyncClient]:
    """Fixture to create a Player app instance."""
    respx_transport = MockTransport(respx_mock.async_handler)
    app_transport = ASGITransport(app=player_app)
    async with AsyncClient(
        base_url="http://player.local", transport=TryTransport([respx_transport, app_transport])
    ) as client:
        yield client


@fixture
async def player_supervisor(player_app: FastAPI) -> PlayerSupervisor:
    """Fixture to get the PlayerSupervisor from the Player app."""
    return player_app.state.supervisor


@fixture
async def experiment_manager_app(redis_server_dsn: RedisDsn) -> AsyncGenerator[FastAPI]:
    """Fixture to create an ExperimentManager app instance."""
    app = run_experiment_manager(redis_server_dsn)
    async with LifespanManager(app):
        yield app


@fixture
async def experiment_manager_app_client(
    experiment_manager_app: FastAPI, respx_mock: respx.MockRouter
) -> AsyncGenerator[AsyncClient]:
    """Fixture to create an ExperimentManager app instance."""
    respx_transport = MockTransport(respx_mock.async_handler)
    app_transport = ASGITransport(app=experiment_manager_app)
    async with AsyncClient(
        base_url="http://em.local", transport=TryTransport([respx_transport, app_transport])
    ) as client:
        yield client


@fixture
async def experiment_manager(experiment_manager_app: FastAPI) -> ExperimentManager:
    return experiment_manager_app.state.experiment_manager


@fixture
async def game_app(free_tcp_port_factory: FreePortFactory) -> AsyncGenerator[FastAPI]:
    """Fixture to create a Game app instance."""
    port = free_tcp_port_factory()
    app = run_game_instance(port=port)
    async with LifespanManager(app):
        # Ensure the GameSupervisor is ready before yielding
        async for _ in periodic(1):
            if app.state.state_monitor.ready_event.is_set():
                break
        yield app


@fixture
async def game_app_client(
    game_app: FastAPI, respx_mock: respx.MockRouter
) -> AsyncGenerator[AsyncClient]:
    """Fixture to create a Game app instance."""
    respx_transport = MockTransport(respx_mock.async_handler)
    app_transport = ASGITransport(app=game_app)
    async with AsyncClient(
        base_url="http://gameserver.local",
        transport=TryTransport([respx_transport, app_transport]),
    ) as client:
        yield client


@fixture
async def game_supervisor(game_app: FastAPI) -> GameSupervisor:
    """Fixture to create a GameSupervisor instance."""
    return game_app.state.game_supervisor


@fixture
async def defuser_player_app(
    free_tcp_port_factory: FreePortFactory, redis_server_dsn: RedisDsn
) -> AsyncGenerator[FastAPI]:
    """Fixture to create a Player app instance."""
    port = free_tcp_port_factory()
    app = run_player(port=port, redis_dsn=redis_server_dsn, hydra_overrides=["model=test_defuser"])
    async with LifespanManager(app):
        yield app


@fixture
async def defuser_player_app_client(
    defuser_player_app: FastAPI, respx_mock: respx.MockRouter
) -> AsyncGenerator[AsyncClient]:
    """Fixture to create a Player app instance."""
    respx_transport = MockTransport(respx_mock.async_handler)
    app_transport = ASGITransport(app=defuser_player_app)
    async with AsyncClient(
        base_url="http://defuserplayer.local",
        transport=TryTransport([respx_transport, app_transport]),
    ) as client:
        yield client


@fixture
async def defuser_player_supervisor(defuser_player_app: FastAPI) -> PlayerSupervisor:
    """Fixture to get the PlayerSupervisor from the Player app."""
    return defuser_player_app.state.supervisor


@fixture
@parametrize("component", [KtaneComponent.big_button])
@parametrize("thinking_framework", ["act"])
def experiment_spec(component: KtaneComponent, thinking_framework: str) -> ExperimentSpec:
    return ExperimentSpec(
        mission_spec=KtaneMissionSpec(
            seed=234,
            time_limit=60,
            num_strikes_allowed=3,
            components=[component],
            optional_widgets=1,
        ),
        condition="single_module",
        defuser_name="test-defuser",
        defuser_protocol=PlayerProtocol(
            role="defuser",
            communication_style="sync",
            is_playing_alone=True,
            include_manual=True,
            thinking_framework=thinking_framework,
            allow_thoughts_output=False,
            allow_thoughts_in_history=False,
            allow_outputs_in_history=True,
        ),
        expert_name=None,
        expert_protocol=None,
    )
