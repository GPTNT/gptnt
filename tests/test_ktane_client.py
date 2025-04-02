import httpx
import pytest
import pytest_asyncio
import respx
from pytest_cases import fixture
from typing_extensions import AsyncGenerator

from gptnt.ktane.client import KtaneClient
from gptnt.ktane.structures import KtaneComponent, KtaneMissionSpec

JSON_KEY = "message"


@pytest_asyncio.fixture
async def client(host: str, port: int) -> AsyncGenerator[KtaneClient, None]:
    """Provides an instance of the Ktane Client for testing."""
    http_client = httpx.AsyncClient(base_url=f"http://{host}:{port}")
    async with KtaneClient(client=http_client) as client:
        yield client


@fixture
def mission_spec() -> KtaneMissionSpec:
    mission_spec = KtaneMissionSpec(
        seed=123,  # noqa: WPS432
        time_limit=300,  # noqa: WPS432
        num_strikes_allowed=3,
        needy_time=90,  # noqa: WPS432
        force_modules_to_front=True,
        optional_widgets=5,
        components=[KtaneComponent.wires, KtaneComponent.big_button],
    )
    return mission_spec


@respx.mock
@pytest.mark.asyncio
async def test_healthcheck_returns_true(client: KtaneClient) -> None:
    _ = respx.get(f"{client.client.base_url}/health").mock(
        return_value=httpx.Response(httpx.codes.OK)
    )

    is_healthy = await client.healthcheck()
    assert is_healthy is True


@respx.mock
@pytest.mark.asyncio
async def test_healthcheck_returns_false_and_no_exception(client: KtaneClient) -> None:
    _ = respx.get(f"{client.client.base_url}/health").mock(
        return_value=httpx.Response(httpx.codes.BAD_REQUEST)
    )

    is_healthy = await client.healthcheck()
    assert is_healthy is False


@respx.mock
@pytest.mark.asyncio
async def test_start_mission_returns_true_on_success(
    client: KtaneClient, mission_spec: KtaneMissionSpec
) -> None:
    route = respx.get(f"{client.client.base_url}/startMission").mock(
        return_value=httpx.Response(httpx.codes.OK, json={JSON_KEY: "Mission started"})
    )
    start_mission_response = await client.start_mission(mission_spec)
    assert route.called is True
    assert start_mission_response is True


@respx.mock
@pytest.mark.asyncio
async def test_start_mission_returns_false_on_failing(
    client: KtaneClient, mission_spec: KtaneMissionSpec
) -> None:
    route = respx.get(f"{client.client.base_url}/startMission").mock(
        return_value=httpx.Response(httpx.codes.BAD_REQUEST, json={JSON_KEY: "Mission started"})
    )
    start_mission_response = await client.start_mission(mission_spec)
    assert route.called is True
    assert start_mission_response is False
