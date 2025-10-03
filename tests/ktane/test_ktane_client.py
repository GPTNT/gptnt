import base64
from pathlib import Path

import httpx
import pytest
import respx
from pytest_cases import fixture

from gptnt.ktane.actions import GameActionType, KtaneAction
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.game import GameState
from gptnt.ktane.state.modules import KtaneComponent


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
@pytest.mark.anyio
async def test_healthcheck_returns_true(ktane_client: KtaneClient) -> None:
    _ = respx.get(f"{ktane_client.client.base_url}/health").mock(
        return_value=httpx.Response(httpx.codes.OK, text=GameState.lights_on.value)
    )

    is_healthy = await ktane_client.healthcheck()
    assert is_healthy is True


@respx.mock
@pytest.mark.anyio
async def test_healthcheck_returns_false_and_no_exception(ktane_client: KtaneClient) -> None:
    _ = respx.get(f"{ktane_client.client.base_url}/health").mock(
        return_value=httpx.Response(httpx.codes.BAD_REQUEST)
    )

    is_healthy = await ktane_client.healthcheck()
    assert is_healthy is False


@respx.mock
@pytest.mark.anyio
async def test_start_mission_returns_true_on_success(
    ktane_client: KtaneClient, mission_spec: KtaneMissionSpec
) -> None:
    route = respx.get(f"{ktane_client.client.base_url}/startMission").mock(
        return_value=httpx.Response(httpx.codes.OK, text="Mission started")
    )
    start_mission_response = await ktane_client.start_mission(mission_spec)
    assert route.called is True
    assert start_mission_response is True


@respx.mock
@pytest.mark.anyio
async def test_start_mission_returns_false_on_failing(
    ktane_client: KtaneClient, mission_spec: KtaneMissionSpec
) -> None:
    route = respx.get(f"{ktane_client.client.base_url}/startMission").mock(
        return_value=httpx.Response(httpx.codes.BAD_REQUEST, text="Mission failed")
    )
    with pytest.raises(httpx.HTTPStatusError):
        _ = await ktane_client.start_mission(mission_spec)
    assert route.called is True


@respx.mock
@pytest.mark.anyio
async def test_get_observation_returns_screenshot_as_bytes(
    ktane_client: KtaneClient, screenshot: str
) -> None:
    route = respx.get(f"{ktane_client.client.base_url}/buffer").mock(
        return_value=httpx.Response(
            httpx.codes.OK, json={"frames": [screenshot], "segmentation": None}
        )
    )
    screenshot_response = await ktane_client.get_observation_frames()
    assert route.called is True
    assert screenshot_response.frames[0] == screenshot


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


# @respx.mock
# @pytest.mark.anyio
# @pytest.mark.skip(reason="Needs updating to phase3")
# async def test_get_observation_frames_resizes_image(client: KtaneClient, screenshot: str) -> None:
#     """Test that the KtaneClient correctly resizes the image."""
#     # Mock the get_observation_frames method to return the image and segmentation bytes
#     _ = respx.get(f"{client.client.base_url}/buffer").mock(
#         return_value=httpx.Response(
#             httpx.codes.OK, json={"frames": [screenshot], "segmentation": None}
#         )
#     )

#     # Add resizer to client
#     client.image_resizer = ImageResizer(target_width=100, target_height=200)

#     # Get the observation
#     observation: Observation = await client.get_observation_frames()
#     last_frame = observation.frames[-1]
#     assert isinstance(last_frame, bytes)

#     last_frame_image = load_observation_from_bytes(last_frame)
#     # Check that the observation is resized
#     assert last_frame_image.size == (
#         client.image_resizer.target_width,
#         client.image_resizer.target_height,
#     )


# @fixture(scope="session")
# def screenshot_segmentation_pair(fixture_path: Path) -> tuple[bytes, bytes]:
#     """Fixture to provide a screenshot and segmentation pair."""
#     image_bytes = fixture_path.joinpath("screenshot1.png").read_bytes()
#     segm_bytes = fixture_path.joinpath("segmentation1.png").read_bytes()
#     return image_bytes, segm_bytes


# @respx.mock
# @pytest.mark.anyio
# @pytest.mark.parametrize("action_type", list(GameActionType))
# @pytest.mark.skip(reason="Needs updating to phase3")
# async def test_set_of_mark_actions_are_converted_to_relative_coordinates(
#     client_with_som: KtaneClient,
#     screenshot_segmentation_pair: tuple[bytes, bytes],
#     mocker: MockerFixture,
#     action_type: GameActionType,
#     bomb_state_json: dict[str, Any],
# ) -> None:
#     """Test that the KtaneAction correctly converts to query parameters."""
#     assert isinstance(client_with_som.set_of_marks_painter, SetOfMarksHandler)

#     # Load an image and segmentation mask
#     image_bytes, segm_bytes = screenshot_segmentation_pair

#     # Mock the get_observation method to return the image and segmentation bytes
#     _ = respx.get(f"{client_with_som.client.base_url}/buffer").mock(
#         return_value=httpx.Response(
#             httpx.codes.OK,
#             json={
#                 "frames": [base64.b64encode(image_bytes).decode("utf-8")],
#                 "segmentation": base64.b64encode(segm_bytes).decode("utf-8"),
#             },
#         )
#     )
#     _ = respx.get(f"{client_with_som.client.base_url}/action").mock(
#         return_value=httpx.Response(httpx.codes.OK, json=bomb_state_json)
#     )

#     som_mark_style = client_with_som.set_of_marks_painter._mark_type
#     som_mark_type = str if som_mark_style == "alphabet" else int
#     som_location = "A" if som_mark_style == "alphabet" else 1

#     # Get the observation
#     _ = await client_with_som.get_observation_frames()
#     # Make sure that the mapping of marks to coords exists
#     assert client_with_som.set_of_marks_painter._mark_to_coordinate is not None

#     action = KtaneBaseAction[som_mark_type](
#         action=action_type,
#         location=som_location if action_type in GameActionType.require_location() else None,
#     )

#     # Call the method
#     spy = mocker.spy(SetOfMarksHandler, "mark_to_coordinate")
#     _ = await client_with_som.send_action(action)

#     if action_type in GameActionType.require_location():
#         assert spy.called is True
#         assert (
#             spy.spy_return
#             == client_with_som.set_of_marks_painter._mark_to_coordinate[som_location]
#         )
#     else:
#         # If the action does not require a location, we should not call the mark_to_coordinate method
#         assert spy.called is False
