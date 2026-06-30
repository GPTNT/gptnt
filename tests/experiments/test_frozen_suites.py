"""A suite, and the missions it loads, are frozen: changing either requires bumping its `revision`.

Each suite is pinned to `(revision, suite_digest)`. A change to the suite config, or to any mission
file it loads, fails this test; update the snapshot with `--inline-snapshot=fix` only after bumping
the suite's `revision`.

A separate check holds each suite's `name` to its filename, so a `suites=` reference and the
stamped `suite_name` stay in sync.
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


def _load_suite(suite_name: str) -> Suite:
    """Compose and instantiate one suite exactly as generation does."""
    return hydra.utils.instantiate(
        load_config(config_name=CONFIG_NAME, overrides=[f"suites={suite_name}"]).suite
    )


def _frozen() -> dict[str, dict[str, Any]]:
    """Every suite's revision and the digest of its config plus its resolved missions."""
    frozen: dict[str, dict[str, Any]] = {}
    for stem in discover_suites():
        suite = _load_suite(stem)
        frozen[suite.name] = {"revision": suite.revision, "digest": suite.suite_digest}
    return frozen


def test_suites_are_frozen() -> None:
    """A suite (or its missions) changing without a `revision` bump fails this test."""
    assert _frozen() == snapshot(
        {
            "multi-self-async": {"revision": 1, "digest": "a02fed7179d4fd142d34324d720468ba"},
            "multi-self-sync": {"revision": 1, "digest": "365784c76589a9c1a2b6f1708f068e92"},
            "single-pairwise-sync": {"revision": 1, "digest": "ecb690fb90927c540b3940afc0c458d0"},
            "single-parametric-sync": {
                "revision": 1,
                "digest": "5460034434039828c73292f7f3fc5867",
            },
            "single-self-async": {"revision": 1, "digest": "a47edcc5dece4e117f0e7a145ed197c5"},
            "single-solo-player-sync": {
                "revision": 1,
                "digest": "125050b2dc2695dcc0fd887c2d1ad2eb",
            },
        }
    )


def test_suite_name_matches_filename() -> None:
    """Each suite's `name` must equal its config filename, so references can't drift."""
    mismatched = {
        stem: name for stem in discover_suites() if (name := _load_suite(stem).name) != stem
    }
    assert not mismatched, f"suite name != filename for: {mismatched}"
