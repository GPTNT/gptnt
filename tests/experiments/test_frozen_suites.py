"""A suite, and the missions it loads, are frozen: changing either requires bumping its `revision`.

Each suite is pinned to `(revision, suite_digest)`. A change to the suite config, or to any mission
file it loads, fails this test; update the snapshot with `--inline-snapshot=fix` only after bumping
the suite's `revision`.

A separate check holds each suite's `id` to its filename, so a `suites=` reference and the stamped
`suite_id` stay in sync.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import hydra
from inline_snapshot import snapshot

from gptnt.cli.config_discovery import discover_suites
from gptnt.common.hydra import load_config
from gptnt.experiments.generation.pipeline import CONFIG_NAME

if TYPE_CHECKING:
    from gptnt.experiments.suite import Suite


def _load_suite(suite_id: str) -> Suite:
    """Compose and instantiate one suite exactly as generation does."""
    return hydra.utils.instantiate(
        load_config(config_name=CONFIG_NAME, overrides=[f"suites={suite_id}"]).suite
    )


def _frozen() -> dict[str, dict[str, Any]]:
    """Every suite's revision and the digest of its config plus its resolved missions."""
    frozen: dict[str, dict[str, Any]] = {}
    for stem in discover_suites():
        suite = _load_suite(stem)
        frozen[suite.id] = {"revision": suite.revision, "digest": suite.suite_digest}
    return frozen


def test_suites_are_frozen() -> None:
    """A suite (or its missions) changing without a `revision` bump fails this test."""
    assert _frozen() == snapshot(
        {
            "multi-self-async": {"revision": 1, "digest": "d2fbaf914b91bc6c7d1330398ff6828d"},
            "multi-self-sync": {"revision": 1, "digest": "7f6f123beb9749eae6a62cb390384c6f"},
            "single-pairwise-sync": {"revision": 1, "digest": "b33a240fb0eff7737f10b1d15f6af392"},
            "single-parametric-sync": {
                "revision": 1,
                "digest": "70e5e223d5bbc85898f6366440c50060",
            },
            "single-self-async": {"revision": 1, "digest": "8c954ffda4086fd3ed22c95eb1233638"},
            "single-solo-player-sync": {
                "revision": 1,
                "digest": "777fc8f490217756d7a32b780ab1bc83",
            },
        }
    )


def test_suite_id_matches_filename() -> None:
    """Each suite's `id` must equal its config filename, so references can't drift."""
    mismatched = {
        stem: suite_id for stem in discover_suites() if (suite_id := _load_suite(stem).id) != stem
    }
    assert not mismatched, f"suite id != filename for: {mismatched}"
