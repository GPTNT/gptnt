from pydantic import TypeAdapter

from gptnt.ktane.state.modules import InteractiveModuleState, ModuleStates, MorseCodeModuleState


def test_known_module_uses_typed_state() -> None:
    """A known identifier selects its module-specific state model."""
    state = TypeAdapter(ModuleStates).validate_python(
        {
            "name": "Morse",
            "onFront": True,
            "index": 0,
            "isSolved": False,
            "inFocus": False,
            "sequence": "boxes",
            "currentFrequency": 505,
            "correctFrequency": 535,
        }
    )

    assert isinstance(state, MorseCodeModuleState)
    assert state.name == "Morse"


def test_unknown_module_uses_generic_state() -> None:
    """An unknown identifier retains its ID in the generic state model."""
    state = TypeAdapter(ModuleStates).validate_python(
        {
            "name": "SomeCommunityModule",
            "onFront": True,
            "index": 0,
            "isSolved": False,
            "inFocus": False,
        }
    )

    assert isinstance(state, InteractiveModuleState)
    assert state.name == "SomeCommunityModule"
