"""Stable identity hashing behavior."""

from gptnt.common.hashing import stable_digest


def test_stable_digest_preserves_the_existing_json_encoding() -> None:
    """The persisted digest includes stdlib JSON separators and ASCII escaping."""
    assert stable_digest({"b": [2, 1], "a": "café"}) == "eee56a43aff148d9409d413f5b1723fa"
