from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter

_MODEL_SETTINGS_ADAPTER = TypeAdapter(dict[str, JsonValue])
_IGNORED_MODEL_SETTINGS = frozenset(
    (
        # Request transport and execution limits.
        "extra_headers",
        "timeout",
        # Routing and throughput controls.
        "anthropic_service_tier",
        "anthropic_speed",
        "google_cloud_service_tier",
        "openai_service_tier",
        "service_tier",
        # Prompt-cache mechanics.
        "anthropic_cache",
        "anthropic_cache_instructions",
        "anthropic_cache_messages",
        "anthropic_cache_tool_definitions",
        "openai_prompt_cache_key",
        "openai_prompt_cache_retention",
        # Storage, billing, and abuse-monitoring metadata.
        "anthropic_metadata",
        "google_labels",
        "openai_store",
        "openai_user",
        # Response metadata and usage reporting not consumed by the benchmark.
        "google_logprobs",
        "google_top_logprobs",
        "openai_continuous_usage_stats",
        "openai_logprobs",
        "openai_top_logprobs",
        # Streaming behavior that preserves the completed tool call.
        "anthropic_eager_input_streaming",
    )
)


def fingerprint_model_settings(
    settings: Mapping[str, object] | None,
) -> dict[str, JsonValue] | None:
    """Return JSON model settings that affect model inputs or generation.

    Operational top-level settings are omitted. All other keys, including provider-specific and
    nested settings, affect identity. The settings are configuration data, so unsupported runtime
    objects fail validation instead of being converted heuristically.
    """
    if not settings:
        return None

    selected = {
        key: setting_value
        for key, setting_value in settings.items()
        if key not in _IGNORED_MODEL_SETTINGS
    }
    if not selected:
        return None
    return _MODEL_SETTINGS_ADAPTER.validate_python(selected)
