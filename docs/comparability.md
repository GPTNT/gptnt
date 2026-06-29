# Comparability

GPTNT measures how well models defuse KTANE bombs. Two recorded results are comparable when they were
measured the same way. This document defines what that means and how a result records it.

## The taxonomy

A run composes four things, each with one home:

- **Suite** (`configs/suites/<id>.yaml`) — what is measured. A frozen mission set, the per-role
  interaction protocols, the matchup that pairs players, the required modalities, and a revision. A
  suite names no models and no capabilities.
- **Mission library** (`configs/missions/<set>/`) — frozen `KtaneMissionSpec` JSON, grouped into
  named sets that a suite loads by path (`configs/missions/README.md`).
- **Model** (`configs/model/<model>.yaml`) — a contestant. Its `PlayerCapabilities` set how it is
  run: image size, observation budget, thinking method, and so on.
- **Run** (`run.yaml`, `RunManifest`) — one invocation. It selects suites and a roster of models.

The word "experiment" means only the recorded unit: one (defuser, expert, mission) attempt.

## The comparability key

Two recorded results are comparable when all three match:

    suite_id  +  suite_revision  +  capability_fingerprint

Reproducing a result also needs `gptnt_version` and `git_sha`.

The three meet only on the recorded result (`ExperimentSummary`). `suite_id` and `suite_revision`
come from the suite. The `capability_fingerprint` comes from the model. A suite names no model and a
model names no suite, so the result is the only object that holds both.

## Suites and their digests

A suite exposes three digests. `config_digest` covers its config — the mission-set path, protocols,
matchup, and modalities — and reads no files. `missions_digest` covers the contents of its mission
set, read from disk. `suite_digest` combines the two.

`tests/experiments/test_frozen_suites.py` pins each suite's `(revision, suite_digest)`. Changing the
config, or any mission file the suite loads, fails that test unless the suite's `revision` is bumped
in the same change. A bumped `revision` marks a new measurement, not pooled with the old one.

The same test checks that a suite's `id` equals its filename, so a `run.yaml` reference and the
recorded `suite_id` stay in sync.

## The capability fingerprint

`PlayerCapabilities.fingerprint` is a stable digest of a model's full capabilities. A model is judged
at the best of its abilities, so its capabilities define it, and they are never compared across
models. The fingerprint catches one case: the same `player_name` run under two different capability
sets. Its fingerprint then changes, and results that would otherwise pool under that name separate.

It is recorded per side, as `defuser_capability_fingerprint` and `expert_capability_fingerprint`. In
self-play both sides are the same model, so the two match.

## Identity addressing

Three layers of identity, each with its own key:

- **experiment** → `attempt_name` — the logical attempt.
- **execution** → `session_id` — one physical run of an attempt.
- **conversation** → `(session_id, role)` — one player's transcript within a run.
