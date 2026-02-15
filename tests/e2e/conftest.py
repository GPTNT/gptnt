import os
from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager
from typing import cast, override

import anyio
import httpx
import pytest
import respx
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from faststream import FastStream, TestApp
from pydantic import RedisDsn
from pytest_cases import fixture, param_fixture, parametrize
from respx.models import PassThrough, ResolvedRoute, SideEffectError
from respx.transports import TryTransport

from gptnt.common.paths import Paths
from gptnt.entrypoints.run_experiment_manager import run as run_experiment_manager
from gptnt.entrypoints.run_game_instance import main as run_game_instance
from gptnt.entrypoints.run_player import main as run_player
from gptnt.experiments.experiments import ExperimentSpec
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.players.specification import PlayerProtocol
from gptnt.services.experiment_manager.experiment_manager import ExperimentManager
from gptnt.services.game.service import GameService
from gptnt.services.player.service import PlayerService

paths = Paths()

pytestmark = pytest.mark.anyio


class AutoPassThroughRouter(respx.MockRouter):
    """A modified router that automatically passes through requests that are not mocked.

    Basically, all that matters is that if a request is not mocked, we are going to raise the
    PassThrough exception so that it can be handled by another transport (e.g. ASGITransport).
    """

    @classmethod
    def from_mock_router(cls, mock_router: respx.MockRouter) -> "AutoPassThroughRouter":
        """Create a AutoPassThroughRouter from an existing respx.MockRouter instance.

        Just do it by patching the method since that's all that matters.
        """
        mock_router.resolver = cls.resolver.__get__(mock_router, respx.MockRouter)
        new_router = cast("AutoPassThroughRouter", mock_router)
        return new_router

    @contextmanager
    @override
    def resolver(self, request: httpx.Request) -> Generator[ResolvedRoute, None, None]:  # noqa: WPS238 WPS231
        resolved = ResolvedRoute()

        try:  # noqa: WPS229
            yield resolved

            # Note: I have removed the section that auto-mocks a 200 response, instead, we are
            # going to raise PassThrough so that another transport can handle it.
            if resolved.response == request or (resolved.route is None):
                # Pass-through request
                raise PassThrough(  # noqa: TRY301
                    f"Request marked to pass through: {request!r}",
                    request=request,
                    origin=resolved.route,
                )

            else:
                # Mocked response
                assert isinstance(resolved.response, httpx.Response)

        except SideEffectError as error:
            self.record(request, response=None, route=error.route)
            raise error.origin from error
        except PassThrough:
            self.record(request, response=None, route=resolved.route)
            raise
        else:
            self.record(request, response=resolved.response, route=resolved.route)


@fixture(autouse=True)
async def respx_mock(respx_mock: respx.MockRouter) -> AsyncGenerator[AutoPassThroughRouter]:
    yield AutoPassThroughRouter.from_mock_router(respx_mock)


@fixture(autouse=True, scope="session")
def setup_env_vars() -> None:
    """Fixture to set up environment variables for the tests."""
    os.environ["TESTING"] = "1"


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
async def player_app(redis_server_dsn: RedisDsn, player_role: str) -> AsyncGenerator[FastStream]:
    """Fixture to create a Player app instance."""
    app = run_player(redis_dsn=redis_server_dsn, hydra_overrides=[f"model={player_role}"])
    test_app = TestApp(app)
    async with test_app:
        yield test_app.app  # pyright: ignore[reportReturnType]


@fixture
async def player_service(player_app: FastStream) -> PlayerService:
    """Fixture to get the PlayerService from the Player app."""
    await anyio.sleep(5)
    return player_app.context.get("player_service")


# @fixture
# async def player_app_client(
#     player_app: FastAPI, respx_mock: respx.MockRouter
# ) -> AsyncGenerator[AsyncClient]:
#     """Fixture to create a Player app instance."""
#     respx_transport = MockTransport(respx_mock.async_handler)
#     app_transport = ASGITransport(app=player_app)
#     async with AsyncClient(
#         base_url="http://player.local", transport=TryTransport([respx_transport, app_transport])
#     ) as client:
#         yield client


@fixture
async def experiment_manager_app(redis_server_dsn: RedisDsn) -> AsyncGenerator[FastAPI]:
    """Fixture to create an ExperimentManager app instance."""
    app = run_experiment_manager(redis_server_dsn)
    async with LifespanManager(app):
        yield app


@fixture
async def experiment_manager_app_client(
    experiment_manager_app: FastAPI, respx_mock: respx.MockRouter
) -> AsyncGenerator[httpx.AsyncClient]:
    """Fixture to create an ExperimentManager app instance."""
    respx_transport = httpx.MockTransport(respx_mock.async_handler)
    app_transport = httpx.ASGITransport(app=experiment_manager_app)
    async with httpx.AsyncClient(
        base_url="http://em.local", transport=TryTransport([respx_transport, app_transport])
    ) as client:
        yield client


@fixture
async def experiment_manager(experiment_manager_app: FastAPI) -> ExperimentManager:
    return experiment_manager_app.state.experiment_manager


@fixture
async def game_app(redis_server_dsn: RedisDsn) -> AsyncGenerator[FastStream]:
    """Fixture to create a Game app instance."""
    app = run_game_instance(redis_dsn=redis_server_dsn)
    test_app = TestApp(app)
    async with test_app:
        yield test_app.app  # pyright: ignore[reportReturnType]


@fixture
async def game_service(game_app: FastStream) -> GameService:
    """Fixture to create a GameService instance."""
    # Make sure the EM has the game and player
    await anyio.sleep(15)

    return game_app.context.get("game_service")


# @fixture
# async def game_app_client(
#     game_app: FastAPI, respx_mock: respx.MockRouter
# ) -> AsyncGenerator[AsyncClient]:
#     """Fixture to create a Game app instance."""
#     respx_transport = MockTransport(respx_mock.async_handler)
#     app_transport = ASGITransport(app=game_app)
#     async with AsyncClient(
#         base_url="http://gameserver.local",
#         transport=TryTransport([respx_transport, app_transport]),
#     ) as client:
#         yield client


@fixture
async def defuser_player_app(redis_server_dsn: RedisDsn) -> AsyncGenerator[FastStream]:
    """Fixture to create a Player app instance."""
    app = run_player(redis_dsn=redis_server_dsn, hydra_overrides=["model=test_defuser"])
    test_app = TestApp(app)
    async with test_app:
        yield test_app.app  # pyright: ignore[reportReturnType]


@fixture
async def defuser_player_service(defuser_player_app: FastStream) -> PlayerService:
    """Fixture to get the PlayerService from the Player app."""
    await anyio.sleep(5)
    return defuser_player_app.context.get("player_service")


# @fixture
# async def defuser_player_app_client(
#     defuser_player_app: FastAPI, respx_mock: respx.MockRouter
# ) -> AsyncGenerator[AsyncClient]:
#     """Fixture to create a Player app instance."""
#     respx_transport = MockTransport(respx_mock.async_handler)
#     app_transport = ASGITransport(app=defuser_player_app)
#     async with AsyncClient(
#         base_url="http://defuserplayer.local",
#         transport=TryTransport([respx_transport, app_transport]),
#     ) as client:
#         yield client


@fixture
@parametrize("component", [KtaneComponent.big_button])
def experiment_spec(component: KtaneComponent) -> ExperimentSpec:
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
            role="defuser", communication_style="sync", is_playing_alone=True, include_manual=True
        ),
        expert_name=None,
        expert_protocol=None,
    )
