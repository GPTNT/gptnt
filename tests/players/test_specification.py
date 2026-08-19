"""Player capability identity and fingerprint behaviour."""

from pydantic_ai.usage import UsageLimits

from gptnt.common.image_ops import ImageDimensions
from gptnt.players.specification import PlayerCapabilities, PlayerModelConfiguration


def test_evaluation_configuration_changes_the_capability_fingerprint() -> None:
    """The identity payload covers the complete configuration that can affect model output."""
    capabilities = PlayerCapabilities(
        player_name="example-player",
        player_type="ai",
        model=PlayerModelConfiguration(
            name="openai:gpt-5.2",
            provider="openai",
            settings={"temperature": 0.6, "max_tokens": 1_000, "thinking": "minimal"},
        ),
        thinking_method="thinking-out-loud",
        structured_output_mode=None,
        include_schema_in_instructions=True,
        max_observations_per_request=12,
        usage_limits=UsageLimits(input_tokens_limit=20_000, output_tokens_limit=1_000),
        image_dimensions=ImageDimensions(width=512, height=512),
        tokens_per_image=256,
        interaction_location_method="coordinates",
        coordinate_mode="normalised",
        coordinate_scale=1_000,
        preserve_last_frame_for_n_turns=2,
        enable_nobf_generation=False,
    )
    changed = capabilities.model_copy(
        update={"usage_limits": UsageLimits(input_tokens_limit=19_000, output_tokens_limit=1_000)}
    )

    assert capabilities.identity_payload != changed.identity_payload
    assert capabilities.fingerprint != changed.fingerprint
