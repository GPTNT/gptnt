from typing import Any

import httpx
import pytest_asyncio
from pytest_cases import fixture
from typing_extensions import AsyncGenerator

from gptnt.ktane.client import KtaneClient


@pytest_asyncio.fixture
async def client(host: str, port: int) -> AsyncGenerator[KtaneClient, None]:
    """Provides an instance of the Ktane Client for testing."""
    http_client = httpx.AsyncClient(base_url=f"http://{host}:{port}")
    async with KtaneClient(client=http_client) as client:
        yield client


@fixture(scope="session")
def bomb_state_json() -> dict[str, Any]:
    """Return a sample bomb state JSON."""
    return {
        "seed": 998865,
        "maxStrikes": 3,
        "currentStrikes": 0,
        "strikes": [],
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
            {"lightActivated": True, "label": "FRQ", "position": "right", "name": "Indicator"},
            {"portType": [], "position": "bottom", "name": "Port"},
            {"batteriesCount": 1, "batteryType": "D", "position": "left", "name": "Battery"},
            {"batteriesCount": 2, "batteryType": "AA", "position": "bottom", "name": "Battery"},
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
        ],
    }
