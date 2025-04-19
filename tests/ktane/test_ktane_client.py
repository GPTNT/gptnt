import base64
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from pytest_cases import fixture
from pytest_mock import MockerFixture

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.ktane.actions import GameActionType, KtaneAction, KtaneBaseAction
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.processors.image_resizer import ImageResizer
from gptnt.processors.set_of_marks import SetOfMarksHandler


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
        return_value=httpx.Response(httpx.codes.OK, text="Mission started")
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
        return_value=httpx.Response(httpx.codes.BAD_REQUEST, text="Mission failed")
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
def test_ktane_coordinate_action_correctly_converts_to_query_params(
    action_type: GameActionType,
) -> None:
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
async def test_get_observation_resizes_image(client: KtaneClient, screenshot: str) -> None:
    """Test that the KtaneClient correctly resizes the image."""
    # Mock the get_observation method to return the image and segmentation bytes
    _ = respx.get(f"{client.client.base_url}/observation").mock(
        return_value=httpx.Response(
            httpx.codes.OK, json={"screenshot": screenshot, "segmentation": None}
        )
    )

    # Add resizer to client
    client.image_resizer = ImageResizer(target_width=100, target_height=200)

    # Get the observation
    observation = await client.get_observation()
    assert isinstance(observation, bytes)

    observation_image = load_observation_from_bytes(observation)
    # Check that the observation is resized
    assert observation_image.size == (
        client.image_resizer.target_width,
        client.image_resizer.target_height,
    )


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("action_type", list(GameActionType))
async def test_set_of_mark_actions_are_converted_to_relative_coordinates(
    client: KtaneClient,
    fixture_path: Path,
    mocker: MockerFixture,
    action_type: GameActionType,
    bomb_state_json: dict[str, Any],
) -> None:
    """Test that the KtaneAction correctly converts to query parameters."""
    # Create a set of marks painter
    client.set_of_marks_painter = SetOfMarksHandler()

    # Load an image and segmentation mask
    image_bytes = fixture_path.joinpath("screenshot1.png").read_bytes()
    segm_bytes = fixture_path.joinpath("segmentation1.png").read_bytes()

    # Mock the get_observation method to return the image and segmentation bytes
    _ = respx.get(f"{client.client.base_url}/observation").mock(
        return_value=httpx.Response(
            httpx.codes.OK,
            json={
                "screenshot": base64.b64encode(image_bytes).decode("utf-8"),
                "segmentation": base64.b64encode(segm_bytes).decode("utf-8"),
            },
        )
    )
    _ = respx.get(f"{client.client.base_url}/action").mock(
        return_value=httpx.Response(httpx.codes.OK, json=bomb_state_json)
    )

    # Get the observation
    _ = await client.get_observation()
    # Make sure that the mapping of marks to coords exists
    assert client.set_of_marks_painter._mark_to_coordinate is not None

    action = KtaneBaseAction[int](
        action=action_type,
        location=1 if action_type in GameActionType.require_location() else None,
    )

    # Call the method
    spy = mocker.spy(SetOfMarksHandler, "mark_to_coordinate")
    _ = await client.send_action(action)

    if action_type in GameActionType.require_location():
        assert spy.called is True
        assert spy.spy_return == client.set_of_marks_painter._mark_to_coordinate[1]
    else:
        # If the action does not require a location, we should not call the mark_to_coordinate method
        assert spy.called is False


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("action_type", list(GameActionType))
async def test_send_action_returns_bomb_state(
    client: KtaneClient, action_type: GameActionType, bomb_state_json: dict[str, Any]
) -> None:
    action_endpoint = respx.get(f"{client.client.base_url}/action").mock(
        return_value=httpx.Response(httpx.codes.OK, json=bomb_state_json)
    )

    location = {"x_pos": 0.5, "y_pos": 0.5}

    action = KtaneAction(
        action=action_type,
        location=location if action_type in GameActionType.require_location() else None,
    )

    bomb_state = await client.send_action(action)
    assert isinstance(bomb_state, BombState)
    assert action_endpoint.called is True
