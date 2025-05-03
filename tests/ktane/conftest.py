from typing import Any

import httpx
import pytest_asyncio
from pytest_cases import fixture, parametrize
from pytest_mock import MockerFixture
from typing_extensions import AsyncGenerator

from gptnt.ktane.client import KtaneClient
from gptnt.players.actions import SetOfMarksLocation
from gptnt.processors.image_resizer import ImageResizer
from gptnt.processors.labels.drawing import AnnotationBackgroundParams, AnnotationTextParams
from gptnt.processors.set_of_marks import MaskDrawingParams, SetOfMarksHandler


@pytest_asyncio.fixture
async def client(host: str, port: int, mocker: MockerFixture) -> KtaneClient:
    """Provides an instance of the Ktane Client for testing."""
    ktane_client = KtaneClient(url=f"http://{host}:{port}")
    type(ktane_client).client = mocker.PropertyMock(  # pyright: ignore[reportAttributeAccessIssue]
        return_value=httpx.AsyncClient(base_url=f"http://{host}:{port}")
    )
    return ktane_client


@fixture
@parametrize("mark_type", ["alphabet", "number"], ids=["mark_type=alphabet", "mark_type=int"])
def set_of_marks_handler(mark_type: type[SetOfMarksLocation]) -> SetOfMarksHandler:
    annotation_text_params = AnnotationTextParams(
        font=0, font_scale=0.5, thickness=1, space_between_boxes=2
    )
    annotation_background_params = AnnotationBackgroundParams(padding=0, alpha=0.5)
    mask_drawing_params = MaskDrawingParams(
        mask_thickness=1, soft_mask_alpha=0.5, bw_outside_mask=False
    )
    som_handler = SetOfMarksHandler(
        annotation_background_params=annotation_background_params,
        annotation_text_params=annotation_text_params,
        mask_drawing_params=mask_drawing_params,
        mark_type=mark_type,
    )
    return som_handler


@pytest_asyncio.fixture
async def client_with_som(
    client: KtaneClient, set_of_marks_handler: SetOfMarksHandler
) -> AsyncGenerator[KtaneClient, None]:
    """Provides an instance of the Ktane Client with a SoM for testing."""
    client.set_of_marks_painter = set_of_marks_handler
    client.image_resizer = ImageResizer(target_width=100, target_height=100)
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
