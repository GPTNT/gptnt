"""Capture effective model settings as stable, safe benchmark identity data."""

from collections.abc import Mapping, Sequence
from enum import Enum
from math import isfinite
from typing import Any, cast

from pydantic import BaseModel, JsonValue, SecretBytes, SecretStr
from pydantic_core import PydanticSerializationError, to_jsonable_python

from gptnt.players.specification import PlayerCapabilities

_OMITTED_KEYS = frozenset(
    (
        # Hydra construction metadata is not an inference setting.
        "_convert_",
        "_partial_",
        "_recursive_",
        "_target_",
        # Provider transport/authentication state must never enter records or fingerprints.
        "access_token",
        "api_key",
        "auth_token",
        "authorization",
        "base_url",
        "client",
        "client_secret",
        "endpoint",
        "extra_headers",
        "headers",
        "http_client",
        "password",
        "secret",
    )
)


def _canonical_key(key: str) -> str:
    """Normalize a key only for matching against the omission policy."""
    return key.strip().lower().replace("-", "_")


def _normalize(  # noqa: PLR0911, PLR0912, WPS212, WPS231, WPS238
    setting: Any, *, path: str
) -> JsonValue:
    """Recursively convert one setting to deterministic JSON-safe data."""
    if setting is None or isinstance(setting, (bool, int, str)):
        return setting
    if isinstance(setting, float):
        if not isfinite(setting):
            raise ValueError(f"Model setting {path} must be a finite number.")
        return setting
    if isinstance(setting, (SecretStr, SecretBytes)):
        raise TypeError(f"Model setting {path} contains a secret value.")
    if callable(setting):
        raise TypeError(f"Model setting {path} is callable and cannot be fingerprinted.")
    if isinstance(setting, Enum):
        return _normalize(setting.value, path=path)
    if isinstance(setting, BaseModel):
        return _normalize(setting.model_dump(mode="json"), path=path)
    if isinstance(setting, Mapping):
        normalized: dict[str, JsonValue] = {}
        for key, setting_value in setting.items():
            if not isinstance(key, str):
                raise TypeError(f"Model setting {path} contains a non-string mapping key.")
            if _canonical_key(key) in _OMITTED_KEYS:
                continue
            normalized[key] = _normalize(setting_value, path=f"{path}.{key}")
        return normalized
    if isinstance(setting, Sequence) and not isinstance(setting, (bytes, bytearray, str)):
        return [_normalize(entry, path=f"{path}[{index}]") for index, entry in enumerate(setting)]
    if isinstance(setting, (bytes, bytearray)):
        raise TypeError(f"Model setting {path} contains binary data.")

    try:
        json_value = to_jsonable_python(setting)
    except PydanticSerializationError as exc:
        raise TypeError(
            f"Model setting {path} has unsupported type {type(setting).__name__}."
        ) from exc
    if json_value is setting:
        raise TypeError(f"Model setting {path} has unsupported type {type(setting).__name__}.")
    return _normalize(json_value, path=path)


def normalize_model_settings(model_settings: Any) -> dict[str, JsonValue]:
    """Return effective base model settings as stable JSON-safe identity data.

    A callable settings factory can vary per request, so recording it as static identity would be
    false precision. Fail at assembly instead of silently creating an incomplete fingerprint.
    """
    if callable(model_settings):
        raise TypeError("Callable model settings cannot be recorded as static benchmark identity.")
    if model_settings is None:
        return {}
    normalized = _normalize(model_settings, path="model_settings")
    if not isinstance(normalized, dict):
        raise TypeError("Model settings must normalize to a mapping.")
    return cast("dict[str, JsonValue]", normalized)


def capabilities_with_model_settings(
    capabilities: PlayerCapabilities, model_settings: Any
) -> PlayerCapabilities:
    """Create the recorded capabilities value using an agent's effective base settings."""
    return capabilities.model_copy(
        update={"model_settings": normalize_model_settings(model_settings)}
    )
