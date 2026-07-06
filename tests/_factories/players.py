import factory
from pydantic_ai import UsageLimits

from gptnt.players.specification import PlayerCapabilities, PlayerProtocol


class PlayerProtocolFactory(factory.Factory[PlayerProtocol]):
    """Factory for PlayerProtocol instances."""

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = PlayerProtocol

    role = "defuser"
    communication_style = "async"
    is_playing_alone = True
    include_manual = False
    receive_feedback_after_action = False
    allow_magic_actions = False

    class Params:
        # Traits for common variations
        defuser = factory.Trait(role="defuser", is_playing_alone=True)
        expert = factory.Trait(role="expert", is_playing_alone=False)
        solo = factory.Trait(is_playing_alone=True)
        collaborative = factory.Trait(is_playing_alone=False)
        with_magic = factory.Trait(allow_magic_actions=True)
        with_feedback = factory.Trait(receive_feedback_after_action=True)
        with_manual = factory.Trait(include_manual=True)
        sync = factory.Trait(communication_style="sync")


class PlayerCapabilitiesFactory(factory.Factory[PlayerCapabilities]):
    """Factory for PlayerCapabilities instances."""

    class Meta:  # pyright: ignore[reportIncompatibleVariableOverride]
        model = PlayerCapabilities

    player_name = "gpt-5-2"
    player_type = "ai"
    thinking_method = "inner-monologue"
    structured_output_mode = "prompted"
    include_schema_in_instructions = True
    max_observations_per_request = 3
    usage_limits = factory.LazyFunction(UsageLimits)
    interaction_location_method = "set-of-marks"
    preserve_last_frame_for_n_turns = 1
    enable_nobf_generation = True

    class Params:
        # Traits for common variations
        with_limits = factory.Trait(
            usage_limits=factory.LazyFunction(lambda: UsageLimits(input_tokens_limit=100000))
        )
        no_limits = factory.Trait(
            usage_limits=factory.LazyFunction(lambda: UsageLimits(input_tokens_limit=None))
        )
        coordinates = factory.Trait(interaction_location_method="coordinates")
        set_of_marks = factory.Trait(interaction_location_method="set-of-marks")
        thinking_out_loud = factory.Trait(
            thinking_method="thinking-out-loud", structured_output_mode=None
        )
        inner_monologue = factory.Trait(thinking_method="inner-monologue")
        preserve_frames = factory.Trait(preserve_last_frame_for_n_turns=1)
