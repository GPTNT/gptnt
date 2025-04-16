from gptnt.ktane.state.modules import ComplicatedWire, WireSequenceWire, WireSetWire


def test_accept_snake_case() -> None:
    """Test that the snake_case is accepted."""

    assert ComplicatedWire.model_validate(
        {"is_cut": True, "colour": "red", "position": 1, "is_led_on": True, "has_star": False}
    )
    assert WireSetWire.model_validate({"is_cut": True, "colour": "red", "position": 1})
    assert WireSequenceWire.model_validate(
        {"is_cut": True, "colour": "red", "start_position_number": 1, "end_position_letter": "a"}
    )


def test_accept_camel_case() -> None:
    """Test that camelCase is accepted."""

    assert ComplicatedWire.model_validate(
        {"isCut": True, "colour": "red", "position": 1, "isLedOn": True, "hasStar": False}
    )
    assert WireSetWire.model_validate({"isCut": True, "colour": "red", "position": 1})
    assert WireSequenceWire.model_validate(
        {"isCut": True, "colour": "red", "startPositionNumber": 1, "endPositionLetter": "a"}
    )
