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

## The terms and how they connect

```text
DEFINITION  (committed configs)                  CONTESTANT  (committed config)
─────────────────────────────────               ─────────────────────────────
recipe ──(generate-missions)──► mission set      model   configs/model/<id>.yaml
configs/missions/recipes/        *.json files      PlayerCapabilities
                                      ▲               └── fingerprint ──────────┐
suite   configs/suites/<id>.yaml      │                                         │
  missions_path ──────────────────────┘                                        │
  defuser_protocol, expert_protocol   (PlayerProtocol)                          │
  matchup, modality, id, revision                                              │
                                                                               │
  config_digest  +  missions_digest  =  suite_digest                           │
                       └─ pinned per revision by test_frozen_suites            │
                                                                               │
run.yaml (RunManifest):  suites: [ids]   players: [roster]   anchors ──────────┘
                              └───────────┬───────────┘
                                          ▼   generate_specs
                                  ExperimentSpec   (one per mission × pairing × attempt)
                                    suite_id, suite_revision, mission_set,
                                    mission_spec, protocols, player names
                                          │
                                          ▼   play the game, then record
                                  ExperimentSummary   (one recorded "experiment")
                                    suite_id + suite_revision            ◄ from the suite
                                    defuser/expert_capability_fingerprint  ◄ from the model
                                    attempt_name, session_id, outcome, ...

   comparability key  =  suite_id  +  suite_revision  +  capability_fingerprint
```

**Definition — committed configs**

| Term                               | What it is                                                     | Where                                                      |
| ---------------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------- |
| suite                              | the frozen definition of what is measured                      | `configs/suites/<id>.yaml` (`Suite`)                       |
| id                                 | the suite's name; equals its filename                          | `Suite` field                                              |
| revision                           | the suite's version; bumped on any change to what it measures  | `Suite` field                                              |
| modality                           | input modes the suite requires (`vision`, `language`, `audio`) | `Suite` field                                              |
| missions_path                      | repo-relative path to the mission set the suite loads          | `Suite` field                                              |
| matchup                            | how the roster is paired (`pairing_type`)                      | `Suite` field (`SuiteMatchup`)                             |
| defuser_protocol / expert_protocol | a role's behaviour: sync/async, solo, manual                   | `Suite` fields (`PlayerProtocol`)                          |
| mission set                        | a named group of frozen mission files                          | `configs/missions/<set>/`                                  |
| mission                            | one bomb's spec: seed, modules, time limit                     | `*.json` (`KtaneMissionSpec`)                              |
| recipe                             | generates a mission set from seeds                             | `configs/missions/recipes/<set>.yaml` (`MissionGenerator`) |
| model                              | a contestant                                                   | `configs/model/<id>.yaml`                                  |
| PlayerCapabilities                 | how a model is run: image size, observation budget, and so on  | the model config                                           |

**Run and generation**

| Term                | What it is                                                    | Where                                |
| ------------------- | ------------------------------------------------------------- | ------------------------------------ |
| run manifest        | one invocation: which suites, which models                    | `run.yaml` (`RunManifest`)           |
| roster (`players`)  | the models taking part                                        | manifest field                       |
| anchors             | reference models for `with_best_*` matchups                   | manifest field                       |
| generate_specs      | composes a suite plus a roster into specs                     | `experiments.generation.pipeline`    |
| ExperimentGenerator | pairs missions × pairings into specs                          | `experiments.generation.experiments` |
| PairingGenerator    | turns the roster into (defuser, expert) pairs per the matchup | `experiments.generation.pairing`     |
| ExperimentSpec      | the logical spec for one attempt                              | `experiments.spec`                   |
| mission_set         | the set's name (`missions_path` basename); a grouping label   | spec and record field                |
| attempt_name        | the logical attempt's identity                                | `ExperimentSpec` property            |

**Digests and fingerprints**

| Term                                  | What it is                                             | Where                            |
| ------------------------------------- | ------------------------------------------------------ | -------------------------------- |
| stable_digest                         | the hashing primitive: blake2b over sorted JSON        | `common.hashing`                 |
| config_digest                         | digest of a suite's config; reads no files             | `Suite` property                 |
| missions_digest                       | digest of a suite's resolved mission files; reads disk | `Suite` property                 |
| suite_digest                          | `config_digest` and `missions_digest` combined         | `Suite` property                 |
| capability_fingerprint                | digest of a model's full capabilities                  | `PlayerCapabilities.fingerprint` |
| defuser/expert_capability_fingerprint | the per-side capability fingerprint on a result        | `ExperimentSummary`              |

**Result — recorded**

| Term                 | What it is                                                 | Where                    |
| -------------------- | ---------------------------------------------------------- | ------------------------ |
| experiment           | the recorded unit: one (defuser, expert, mission) attempt  | —                        |
| ExperimentDescriptor | runtime identity: the spec, the actual capabilities, uuids | `experiments.descriptor` |
| ExperimentSummary    | one experiment's recorded result, a DB row                 | `experiments.models`     |
| session_id           | one physical run of an attempt                             | record field             |
| (session_id, role)   | one player's conversation within a run                     | —                        |
| comparability key    | `suite_id` + `suite_revision` + `capability_fingerprint`   | on `ExperimentSummary`   |
| reproduce            | the comparability key plus `gptnt_version` and `git_sha`   | `ProvenanceMixin`        |

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
