from typing import Any

from gptnt.ktane.state.modules import ComplicatedWire, WireSequenceWire, WireSetWire


def test_accept_snake_case() -> None:
    """Test that the snake_case is accepted."""
    assert ComplicatedWire.model_validate(
        {"is_cut": True, "color": "red", "position": 1, "is_led_on": True, "has_star": False}
    )
    assert WireSetWire.model_validate({"is_cut": True, "color": "red", "position": 1})
    assert WireSequenceWire.model_validate(
        {"is_cut": True, "color": "red", "start_position_number": 1, "end_position_letter": "a"}
    )


def test_accept_camel_case() -> None:
    """Test that camelCase is accepted."""
    assert ComplicatedWire.model_validate(
        {"isCut": True, "color": "red", "position": 1, "isLedOn": True, "hasStar": False}
    )
    assert WireSetWire.model_validate({"isCut": True, "color": "red", "position": 1})
    assert WireSequenceWire.model_validate(
        {"isCut": True, "color": "red", "startPositionNumber": 1, "endPositionLetter": "a"}
    )


class StateCases:
    def case_sample(self, bomb_state_json: dict[str, Any]) -> dict[str, Any]:
        return bomb_state_json

    def case_from_morse_code(self) -> dict[str, Any]:
        return {
            "seed": 1000,
            "maxStrikes": 3,
            "currentStrikes": 0,
            "isDetonated": False,
            "isSolved": False,
            "isLightOn": True,
            "bombSide": "front",
            "timerModule": {
                "secondsRemaining": 290.366852,
                "onFront": True,
                "index": 0,
                "name": "Timer",
            },
            "widgets": [{"serialNumber": "D24DN6", "position": "left", "name": "SerialNumber"}],
            "modules": [
                {
                    "sequence": "boxes",
                    "currentFrequency": 505,
                    "correctFrequency": 535,
                    "isSolved": False,
                    "inFocus": False,
                    "onFront": False,
                    "index": 5,
                    "name": "Morse",
                }
            ],
            "strikes": [],
        }


# @respx.mock
# @pytest.mark.asyncio
# @pytest.mark.parametrize("action_type", list(GameActionType))
# @parametrize_with_cases("state_json", cases=StateCases)
# async def test_send_action_returns_bomb_state(
#     client: KtaneClient, action_type: GameActionType, state_json: dict[str, Any]
# ) -> None:
#     action_endpoint = respx.get(f"{client.client.base_url}/action").mock(
#         return_value=httpx.Response(httpx.codes.OK, json=state_json)
#     )

#     location = {"x_pos": 0.5, "y_pos": 0.5}

#     action = KtaneAction(
#         action=action_type,
#         location=location if action_type in GameActionType.require_location() else None,
#     )

#     _ = await client.send_action(action)
#     assert action_endpoint.called is True
