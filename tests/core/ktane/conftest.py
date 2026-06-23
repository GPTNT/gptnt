from typing import Any

from pytest_cases import fixture, parametrize

from gptnt.players.locations import SetOfMarksLocation
from gptnt.processors.labels.drawing import AnnotationBackgroundParams, AnnotationTextParams
from gptnt.processors.set_of_marks import MaskDrawingParams, SetOfMarksHandler


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
