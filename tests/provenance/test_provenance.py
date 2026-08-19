"""Behavioral tests for stored provenance validation."""

from typing import Never

import pytest
from pydantic import ValidationError

from gptnt.provenance import Provenance


def _reject_checkout_read(*args: object, **kwargs: object) -> Never:
    """Fail if validation tries to inspect the current checkout."""
    raise AssertionError(f"checkout read during record validation: {args!r}, {kwargs!r}")


@pytest.mark.parametrize(
    ("stored_provenance", "condition"),
    [
        (
            {"gptnt_version": "1.1.1", "git_sha": "abc123"},
            r"release_commit[\s\S]+release_tag[\s\S]+protected_content_modified",
        ),
        (
            {
                "gptnt_version": "1.1.1",
                "release_commit": "abc123",
                "release_tag": "v01.2.3",
                "protected_content_modified": False,
            },
            "release_tag",
        ),
    ],
)
def test_stored_provenance_is_validated_without_reading_the_checkout(
    monkeypatch: pytest.MonkeyPatch, stored_provenance: dict[str, object], condition: str
) -> None:
    """Reject incomplete or malformed stored provenance without checkout fallback."""
    # Any checkout fallback turns this test into an immediate failure.
    monkeypatch.setattr(Provenance, "capture", _reject_checkout_read)

    with pytest.raises(ValidationError, match=condition):
        _ = Provenance.model_validate(stored_provenance)
