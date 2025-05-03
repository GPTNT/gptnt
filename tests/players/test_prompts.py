from gptnt.players.ai.prompts import load_manual_as_prompt


def test_manual_loads_consistently_without_error() -> None:
    """Test that the manual loads from the function without error."""
    manual_prompt = load_manual_as_prompt()
    assert manual_prompt
    manual_prompt = load_manual_as_prompt()
    assert manual_prompt
    manual_prompt = load_manual_as_prompt()
    assert manual_prompt
