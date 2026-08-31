from types import SimpleNamespace

import pytest

from gptnt.cli import integrity


@pytest.fixture(autouse=True)
def clean_benchmark_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give CLI tests a tagged, unmodified benchmark unless a test selects another state."""
    monkeypatch.setattr(
        integrity,
        "check_benchmark_integrity",
        lambda _repository: SimpleNamespace(
            release_tag="v2.0.0",
            release_commit="abc123456789",
            changed_protected_paths=(),
            changed_input_paths=(),
            release_digest=f"sha256:{'1' * 64}",
            checkout_digest=f"sha256:{'1' * 64}",
            protected_content_modified=False,
        ),
    )
