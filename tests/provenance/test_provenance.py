"""Behavioral tests for stored provenance validation."""

from typing import Never

import pytest
from pydantic import ValidationError

from gptnt.provenance import Provenance


def _reject_checkout_read(*args: object, **kwargs: object) -> Never:
    """Fail if validation tries to inspect the current checkout."""
    raise AssertionError(f"checkout read during record validation: {args!r}, {kwargs!r}")


def test_incomplete_stored_provenance_is_rejected_without_reading_the_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject incomplete stored provenance without checkout fallback."""
    # Any checkout fallback turns this test into an immediate failure.
    monkeypatch.setattr(Provenance, "capture", _reject_checkout_read)

    with pytest.raises(
        ValidationError, match=r"release_commit[\s\S]+release_tag[\s\S]+protected_content_modified"
    ):
        _ = Provenance.model_validate({"gptnt_version": "1.1.1", "git_sha": "abc123"})
