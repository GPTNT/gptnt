import base64
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import respx
from pytest_cases import fixture
from typing_extensions import AsyncGenerator

from gptnt.ktane.actions import GameActionType, KtaneAction
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.modules import KtaneComponent

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


@fixture(scope="session")
def screenshot(fixture_path: Path) -> str:
    """Fixture to provide a screenshot."""
    image_bytes = fixture_path.joinpath("screenshot.png").read_bytes()
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    return base64_image


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


@respx.mock
@pytest.mark.asyncio
async def test_get_observation_returns_screenshot_as_bytes(
    client: KtaneClient, screenshot: str
) -> None:
    route = respx.get(f"{client.client.base_url}/screenshot").mock(
        return_value=httpx.Response(httpx.codes.OK, text=screenshot)
    )
    screenshot_response = await client.get_observation()
    assert route.called is True
    assert screenshot_response == base64.b64decode(screenshot)
    assert isinstance(screenshot_response, bytes)


@pytest.mark.parametrize("action_type", list(GameActionType))
def test_ktane_action_correctly_converts_to_query_params(action_type: GameActionType) -> None:
    """Test that the KtaneAction correctly converts to query parameters."""
    location = {"x_pos": 0.5, "y_pos": 0.5}

    action = KtaneAction(
        action=action_type,
        location=location if action_type in GameActionType.require_location() else None,
    )
    query_params = action.to_query_params()
    assert query_params.get("action") == action_type.value

    # Make sure the location is correct
    if action_type in GameActionType.require_location():
        assert query_params.get("x_pos") == str(location["x_pos"])
        assert query_params.get("y_pos") == str(location["y_pos"])

    if action_type not in GameActionType.require_location():
        assert query_params.get("x_pos") is None
        assert query_params.get("y_pos") is None
        assert len(query_params) == 1


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("action_type", list(GameActionType))
async def test_send_action_sends_correct_action(
    client: KtaneClient, action_type: GameActionType
) -> None:
    action_endpoint = respx.get(f"{client.client.base_url}/action").mock(
        return_value=httpx.Response(
            httpx.codes.OK,
            json={
                "seed": 998865,
                "timestamp": 3.76218414,
                "maxStrikes": 3,
                "currentStrikes": 0,
                "isDetonated": False,
                "isSolved": False,
                "isLightOn": True,
                "timerModule": {
                    "secondsRemaining": 8.249501,
                    "onFront": True,
                    "index": 4,
                    "name": "Timer",
                },
                "widgets": [
                    {"serialNumber": "JR2ZR5", "position": "right", "name": "SerialNumber"},
                    {"portType": ["Parallel", "Serial"], "position": "top", "name": "Port"},
                    {
                        "lightActivated": True,
                        "label": "FRQ",
                        "position": "right",
                        "name": "Indicator",
                    },
                    {"portType": [], "position": "bottom", "name": "Port"},
                    {
                        "batteriesCount": 1,
                        "batteryType": "D",
                        "position": "left",
                        "name": "Battery",
                    },
                    {
                        "batteriesCount": 2,
                        "batteryType": "AA",
                        "position": "bottom",
                        "name": "Battery",
                    },
                ],
                "modules": [
                    {
                        "currentWord": "PCVNK",
                        "goalWord": "PLANT",
                        "isSolved": False,
                        "inFocus": False,
                        "onFront": True,
                        "index": 5,
                        "name": "Password",
                    },
                    {
                        "wires": [
                            {"position": 0, "isCut": False, "color": "yellow"},
                            {"position": 1, "isCut": False, "color": "blue"},
                            {"position": 2, "isCut": False, "color": "red"},
                            {"position": 3, "isCut": False, "color": "yellow"},
                            {"position": 4, "isCut": False, "color": "red"},
                            {"position": 5, "isCut": False, "color": "blue"},
                        ],
                        "isSolved": False,
                        "inFocus": False,
                        "onFront": True,
                        "index": 3,
                        "name": "Wires",
                    },
                    {
                        "topLeft": {"symbol": "omega", "color": None},
                        "topRight": {"symbol": "short-i", "color": None},
                        "bottomLeft": {"symbol": "ae", "color": None},
                        "bottomRight": {"symbol": "e-with-diaeresis", "color": None},
                        "isSolved": False,
                        "inFocus": False,
                        "onFront": True,
                        "index": 0,
                        "name": "KeyPad",
                    },
                ],
            },
        )
    )

    location = {"x_pos": 0.5, "y_pos": 0.5}

    action = KtaneAction(
        action=action_type,
        location=location if action_type in GameActionType.require_location() else None,
    )

    bomb_state = await client.send_action(action)
    assert BombState.model_validate(bomb_state)
    assert action_endpoint.called is True
