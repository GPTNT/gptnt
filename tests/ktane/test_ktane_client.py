from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from gptnt.ktane.mission_spec import KtaneMissionConfig

if TYPE_CHECKING:
    import respx

    from gptnt.ktane.client import KtaneClient


@pytest.fixture
def mission_config() -> KtaneMissionConfig:
    return KtaneMissionConfig(
        seed=123,
        rule_seed=47,
        time_limit=300,
        num_strikes_allowed=3,
        needy_time=90,
        force_modules_to_front=True,
        optional_widgets=5,
        components=["Wires", "BigButton"],
        session_id=None,
    )


@pytest.mark.anyio
async def test_healthcheck_returns_true(
    ktane_client: KtaneClient, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(f"{ktane_client.client.base_url}/health").respond(200)

    assert await ktane_client.healthcheck() is True
    assert route.call_count == 1


@pytest.mark.anyio
async def test_healthcheck_returns_false_and_no_exception(
    ktane_client: KtaneClient, respx_mock: respx.MockRouter
) -> None:
    _ = respx_mock.get(f"{ktane_client.client.base_url}/health").respond(400)

    assert await ktane_client.healthcheck() is False


@pytest.mark.anyio
async def test_start_mission_returns_true_on_success(
    ktane_client: KtaneClient, mission_config: KtaneMissionConfig, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(f"{ktane_client.client.base_url}/startMission").respond(200)

    assert await ktane_client.start_mission(mission_config) is True
    assert route.call_count == 1
    request = route.calls.last.request
    expected_config = mission_config.model_copy(
        update={"time_scale": ktane_client.default_game_speed}
    )
    assert list(request.url.params.multi_items()) == list(
        expected_config.to_query_params().multi_items()
    )


@pytest.mark.anyio
async def test_start_mission_raises_on_failure(
    ktane_client: KtaneClient, mission_config: KtaneMissionConfig, respx_mock: respx.MockRouter
) -> None:
    _ = respx_mock.get(f"{ktane_client.client.base_url}/startMission").respond(400)

    with pytest.raises(httpx.HTTPStatusError):
        _ = await ktane_client.start_mission(mission_config)
