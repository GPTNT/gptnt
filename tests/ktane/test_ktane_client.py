from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import httpx
import pytest

from gptnt.ktane.mission_spec import KtaneMissionConfig

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

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


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=httpx.Request("GET", "http://test"))


@pytest.mark.anyio
async def test_healthcheck_returns_true(ktane_client: KtaneClient, mocker: MockerFixture) -> None:
    _ = mocker.patch.object(
        ktane_client.client, "get", new=AsyncMock(return_value=_response(httpx.codes.OK))
    )

    assert await ktane_client.healthcheck() is True


@pytest.mark.anyio
async def test_healthcheck_returns_false_and_no_exception(
    ktane_client: KtaneClient, mocker: MockerFixture
) -> None:
    _ = mocker.patch.object(
        ktane_client.client, "get", new=AsyncMock(return_value=_response(httpx.codes.BAD_REQUEST))
    )

    assert await ktane_client.healthcheck() is False


@pytest.mark.anyio
async def test_start_mission_returns_true_on_success(
    ktane_client: KtaneClient, mission_config: KtaneMissionConfig, mocker: MockerFixture
) -> None:
    request = mocker.patch.object(
        ktane_client.client, "get", new=AsyncMock(return_value=_response(httpx.codes.OK))
    )

    assert await ktane_client.start_mission(mission_config) is True
    assert request.await_args_list[0].kwargs["params"].get("ruleSeed") == "47"


@pytest.mark.anyio
async def test_start_mission_raises_on_failure(
    ktane_client: KtaneClient, mission_config: KtaneMissionConfig, mocker: MockerFixture
) -> None:
    _ = mocker.patch.object(
        ktane_client.client, "get", new=AsyncMock(return_value=_response(httpx.codes.BAD_REQUEST))
    )

    with pytest.raises(httpx.HTTPStatusError):
        _ = await ktane_client.start_mission(mission_config)
