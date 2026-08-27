"""Behavioral tests for stored provenance validation."""

from typing import Never

import pytest
from pydantic import ValidationError

from gptnt.provenance import Provenance

_RELEASE_DIGEST = f"sha256:{'1' * 64}"
_CHECKOUT_DIGEST = f"sha256:{'2' * 64}"


def test_current_provenance_accepts_modified_state_derived_from_digests() -> None:
    provenance = Provenance(
        gptnt_version="2.0.1.dev1+gabc1234",
        release_commit="a1b2c3d4" * 5,
        release_tag="v2.0.1",
        release_protected_content_digest=_RELEASE_DIGEST,
        protected_content_digest=_CHECKOUT_DIGEST,
        protected_content_modified=True,
    )

    assert provenance.protected_content_modified is True


def test_legacy_provenance_without_digests_remains_readable() -> None:
    provenance = Provenance(
        gptnt_version="2.0.0",
        release_commit="a1b2c3d4" * 5,
        release_tag="v2.0.0",
        protected_content_modified=False,
    )

    assert provenance.release_protected_content_digest is None
    assert provenance.protected_content_digest is None


def test_digest_disagreement_with_modified_flag_is_rejected() -> None:
    with pytest.raises(ValidationError, match="protected_content_modified"):
        _ = Provenance(
            gptnt_version="2.0.1",
            release_commit="a1b2c3d4" * 5,
            release_tag="v2.0.1",
            release_protected_content_digest=_RELEASE_DIGEST,
            protected_content_digest=_RELEASE_DIGEST,
            protected_content_modified=True,
        )


def test_one_missing_digest_is_rejected() -> None:
    with pytest.raises(ValidationError, match="digests must both be set or both null"):
        _ = Provenance(
            gptnt_version="2.0.1",
            release_commit="a1b2c3d4" * 5,
            release_tag="v2.0.1",
            release_protected_content_digest=_RELEASE_DIGEST,
            protected_content_modified=False,
        )


def test_malformed_digest_is_rejected() -> None:
    with pytest.raises(ValidationError, match="release_protected_content_digest"):
        _ = Provenance(
            gptnt_version="2.0.1",
            release_commit="a1b2c3d4" * 5,
            release_tag="v2.0.1",
            release_protected_content_digest="sha256:not-a-digest",
            protected_content_digest=_RELEASE_DIGEST,
            protected_content_modified=False,
        )


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
