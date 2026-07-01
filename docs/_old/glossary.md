# Glossary

There are different layers of vocabulary used in this codebase and we have tried to be as consistent as possible. This document defines the terms and their relationships to help readers understand the codebase.

At a high level: a `suite` defines what is measured, a `run` pairs models against it, the game is played, and a result is recorded. The `ExperimentManager` orchestrates the services that run the game and the players.

## The units, and how they nest together

Several nouns name units at different grains.
**These are not synonyms.**
They can be separated in time, in space, and in identity.

- A `suite` and its `mission`s are _what is measured_
- A `run` is _one invocation_ of a suite against a roster of models
- An `experiment` is _one measured cell_ — a mission, pairing, and suite revision
- An `attempt` is _one tracked try_ of an experiment; an experiment can be attempted multiple times
- A `session` is _one physical execution_ of an attempt

It looks something like this:

```text
run (run.yaml)                          one invocation, the widest unit
 ├─ selects suites[]                    each suite = what is measured
 │    └─ loads a mission set
 │         └─ missions[]                each mission = one bomb spec
 └─ supplies a roster of models[]       the contestants
       └─ matchup pairs them            into (defuser, expert) pairings[]
```

```
generate_specs:  suite × roster  ─▶  ExperimentSpec[]   one per (mission × pairing × attempt)

the grains nest:
experiment   (experiment_name)   one mission × pairing × suite-revision: the measured cell
  └ attempt  (attempt_name)      one tracked try of it; one ExperimentSpec, recorded separately
      └ session  (session_id)    one physical execution of the attempt
          └ (session_id, role)   one player's conversation within the session
```

Widest to narrowest:

<dl>
<dt><code>run</code></dt>
<dd>One invocation (<code>run.yaml</code>). Selects suites and a roster, and produces many experiments.</dd>
<dt><code>suite</code></dt>
<dd>The definition of what is measured: a mission set, the per-role protocols, the matchup (self-play, pairwise, etc.), the modalities required by models, and a <code>revision</code>. A run selects one or more suites. A suite is not dependent on a model.</dd>
<dt><code>mission</code></dt>
<dd>One bomb's spec (seed, modules, time limit). A suite contains a set of missions.</dd>
<dt><code>experiment</code></dt>
<dd>One measured cell: a single mission, pairing, and suite revision. Its identity is <code>experiment_name</code>. An experiment can be attempted more than once.</dd>
<dt><code>attempt</code></dt>
<dd>One tracked try of an experiment. Its identity is <code>attempt_name</code> — the <code>experiment_name</code> plus an <code>attempt</code> index. Each attempt is one <code>ExperimentSpec</code>, run and recorded separately.</dd>
<dt><code>session</code></dt>
<dd>One physical execution of an attempt, identified by <code>session_id</code>. Re-running the same attempt yields a new <code>session_id</code>.</dd>
</dl>

The word "experiment" sits at two grains. <code>experiment_name</code> names the cell, and
<code>attempt_name</code> names one try of it. But most <code>Experiment*</code> types live at the
attempt grain despite the name — an <code>ExperimentSpec</code> carries the <code>attempt</code> index,
and an <code>ExperimentSummary</code> is keyed by <code>attempt_name</code> — so "experiment" in code
usually means one attempt.

## Config layer — what is measured, who competes

The config layer holds the frozen, committed YAML that every run resolves through hydra. It splits
along one line. A `suite` plus its `mission set` define _what is measured_. A `model` plus its
`PlayerCapabilities` define _who competes_. A suite names no model and a model names no suite, so the
same bombs measure any contestant and a contestant runs against any suite. The generation layer joins
the two into an `ExperimentSpec`, the unit a run executes and records.

```text
recipe.yaml ──(gptnt generate-missions)──▶ mission set: configs/missions/<set>/*.json
                                                   ▲
                          suite.missions_path ─────┘   (repo-relative)

  configs/suites/<name>.yaml  ─┐
       Suite + protocols       ├──(generate)──▶ ExperimentSpec ──▶ run
  configs/model/<model>.yaml  ─┘
       carries PlayerCapabilities
```

- **`suite`** — one frozen benchmark configuration that defines a comparable set of results: a mission
  set, the per-role interaction protocols, the matchup, and the required modalities. Two runs of the
  same suite at the same `revision` are comparable. Its `config_digest`, `missions_digest`, and
  combined `suite_digest` fingerprint the config and the resolved mission files together, and
  `test_frozen_suites.py` pins `suite_digest` per revision. Lives in `configs/suites/<name>.yaml`
  (`Suite`).
- **`name`** — the suite identifier. It matches the file basename (`single-pairwise-sync.yaml` has
  `name: single-pairwise-sync`) and is excluded from `config_digest`, so renaming a suite does not
  change its measured fingerprint. Recorded on a result as `suite_name`.
- **`revision`** — an integer (`>= 1`) that bumps on any change to what the suite measures. Editing
  the config or any mission file in the set changes `suite_digest`, and the frozen-suite test fails
  until `revision` is bumped in the same change. This is the guard against silently altering a
  benchmark that older results were recorded against.
- **`modality`** — the input modes the suite requires, drawn from `vision`, `language`, and `audio`.
  Stored as a sorted, de-duplicated tuple with at least one entry, so ordering in the YAML does not
  affect the digest.
- **`missions_path`** — the repo-relative path to the `mission set` directory the suite loads. It must
  not be absolute. Its basename is the `mission_set` name (the `mission_set` property), which groups
  attempts and records.
- **`matchup`** (`SuiteMatchup`) — how a run's roster is paired into `(defuser, expert)` games. It
  wraps a single `pairing_type` (a `PairingType`), so the suite fixes the pairing strategy and the
  roster supplies the players.
- **`defuser_protocol`** / **`expert_protocol`** (`PlayerProtocol`) — the per-role rules for a game:
  communication style (`sync` or `async`), whether the player plays alone, whether the manual is in
  the prompt, and the feedback and action permissions. The defuser slot is role-tagged `defuser`; the
  expert slot is a `PlayerProtocol` tagged `expert` or `None`. A solo defuser admits no expert. The
  `role` here (`defuser` or `expert`) is the same `PlayerRole` the rest of the system pairs on.
- **`mission set`** — a named directory of frozen `KtaneMissionSpec` JSON files under
  `configs/missions/<set>/`. These files are the source of truth. A run loads them with
  `load_missions` and never generates. Editing one changes the loading suite's `missions_digest`.
- **`mission`** (`KtaneMissionSpec`) — one frozen bomb configuration: its `components` (up to 11 KTANE
  modules), the `seed`, `time_limit`, allowed strikes, optional widgets, and timing. Its `mission_key`
  (`"{seed}|{sorted modules}"`) is the stable, readable identity that groups records of the same bomb
  across runs.
- **`recipe`** (`MissionGenerator`, configured by `MissionGeneratorConfig`) — the authoring path that
  materialises a `mission set` from seeds and module-sampling rules. A recipe lives at
  `configs/missions/recipes/<set>.yaml` and is run with `gptnt generate-missions <set>`. It records
  how a set was produced so the set is reproducible. A hand-curated set has no recipe. The run path
  never invokes a recipe.
- **`model`** — a contestant, referenced by a `PlayerSpec` (in a `run.yaml` roster) by its
  `configs/model/<model>.yaml` config name. The config carries the `capabilities` block (a
  `PlayerCapabilities`) and the `action_predictor` that wires up the underlying pydantic-ai model. The
  model says nothing about which suite it faces.
- **`PlayerCapabilities`** — the frozen capability set fixed once at instantiation, telling the
  experiment manager what a player is and what it can do for matchmaking. It carries the input
  `image_dimensions` (image size), `max_observations_per_request` (the observation budget), the
  structured-output mode, and the thinking and location facets below. Its `fingerprint` is a stable
  digest of the exact setup.
  - `thinking_method` (`ThinkingMethod`) — a capability facet: `inner-monologue` keeps reasoning in a
    separate `<think>` section, `thinking-out-loud` folds it into the message flow (and forbids
    structured output).
  - `interaction_location_method` (`InteractionLocationMethod`) — a capability facet: whether the
    player points at modules by `set-of-marks` labels or by `coordinates`.

## Generation — config plus roster become specs

A `run manifest` (`run.yaml`) names one or more `suite`s and a `roster` of models. For each suite,
`generate_specs` loads the suite, materialises its missions, turns the roster into `(defuser, expert)`
pairings, and takes the cross product of missions and pairings, expanded by attempt count. The output
is one `ExperimentSpec` per mission × pairing × attempt. This is where the config layer (suites,
protocols, matchup) meets the contestants (the roster), and each `ExperimentSpec` it yields is the
unit the runtime layer submits to the Experiment Manager.

```text
run.yaml (RunManifest: suites + players + anchors)
        │
        │  generate_specs  (per suite: missions × pairings × attempts)
        ▼
ExperimentSpec  (one per mission × pairing × attempt)
```

- **`run manifest`** — the declarative description of a run: which `suite`s to generate, the `roster`
  of players, the `anchors`, room count, and where the resume check reads completion from. Validated
  as a frozen-shaped pydantic model that rejects unknown keys. Lives in `run.yaml` (`RunManifest`).
- **`roster`** — the list of competing models, one `PlayerSpec` each. `PairingGenerator` draws
  `(defuser, expert)` pairs from it according to the suite's matchup. Held in the manifest's `players`
  field, surfaced to generation as `players.all`.
- **`anchors`** — reference models for the `with_best_defuser` and `with_best_expert` matchups: a
  canonical `best_defuser` and `best_expert` that every roster member is paired against. Other
  matchups ignore them. Carried in the manifest's `anchors` field (`Anchors`), resolved to
  `players.best_defuser` / `players.best_expert` in the generator config.
- **`generate_specs`** — the entry point that composes one `suite` plus a `roster` into specs. It
  instantiates the suite, loads its missions, builds pairings with `PairingGenerator`, and hands both
  to `ExperimentGenerator`. Returns the list of `ExperimentSpec` objects for that suite. Lives in
  `experiments.generation.pipeline`.
- **`ExperimentGenerator`** — takes the materialised missions and the pairings and yields their cross
  product, once per attempt up to `attempts_per_mission`. It carries the suite's identity and
  protocols (`mission_set`, `suite_name`, `suite_revision`, `defuser_protocol`, `expert_protocol`)
  onto every spec, and rejects a pairing that names an expert when the suite has no `expert_protocol`.
  Lives in `experiments.generation.experiments`.
- **`PairingGenerator`** — turns the flat `roster` into `(defuser, expert)` `Pairing`s for the suite's
  `pairing_type`: `pairwise`, `with_self`, `no_expert`, or the `with_best_*` matchups against an
  `anchor`. The `with_best_*` types require a `best_model` and drop it from the opposing side. Lives
  in `experiments.generation.pairing`.
- **`ExperimentSpec`** — the logical specification for one attempt, frozen, holding everything the
  Experiment Manager needs: the `KtaneMissionSpec`, the `mission_set`, the suite identity, and each
  role's protocol and player name. Validates that an expert has both a protocol and a name, and that a
  solo defuser has no expert. Lives in `experiments.spec`.
- **`attempt_name`** — the identity of one logical attempt: the `experiment_name` (suite version,
  mission set, communication style, module names, seed, and pairing) suffixed with `_attempt{attempt}`.
  Distinguishes repeat runs of the same mission and pairing.
- **`mission_set`** — the grouping label for the missions a spec came from, the basename of the
  suite's `missions_path` (for example `single_module`). Stamped onto every `ExperimentSpec` and used
  as a component of `experiment_name`.

## Runtime and services — executing the specs

A `service` is a long-running process that does two things: it broadcasts a heartbeat to redis on a
timer, and it registers RPC command handlers on its own redis channels. Only the game and the players
are services. They extend both `HeartbeatBroadcaster` and `BaseRPCService`. Three points untangle the
rest. First, the `ExperimentManager` (EM) is not a service. It broadcasts no heartbeat and answers no
RPC. It reads other processes' heartbeats and orchestrates them, exposing its own readiness over an
HTTP health endpoint instead. Second, `ServiceRegistry` is the lower layer the EM is built on. The
registry discovers services from their heartbeats and expires them when those heartbeats go stale, and
it knows nothing about experiments. The EM subclasses it and adds the experiment concern on top: it
binds three service manifests (game, defuser, expert) into one `Session` per experiment. Third, a
`Session` and the recorded `session_id` are one entity. The `session_id` is the Session's
`experiment_uuid`, carried on the `ExperimentDescriptor` and stamped into structlog context and timing
spans. Two states run orthogonally: `ServiceManifest.state` is the EM's orchestration view (`idle`,
`in_experiment`, `cleanup`, `not_ready`), while a service's own `ReadyState` and domain state
(`PlayerState`, `GameState`) ride inside its `Heartbeat`. A service can report `ready` while the EM
holds its manifest at `cleanup`. redis carries both concerns on separate paths: heartbeats are TTL'd
hashes under `heartbeat:*` keys for discovery, and FastStream RPC runs commands over per-uuid channels
for control.

```text
ProcessOrchestrator / spawn
   │  starts each as its own process
   ├──────────────┬──────────────────┬──────────────────┐
   ▼              ▼                  ▼                  ▼
ExperimentManager  GameService     PlayerService      PlayerService
(FastAPI, not a    (defuser room)  (defuser)          (expert)
 service)               │               │                  │
                        └───── heartbeat:* (TTL hashes) ────┤
                                        │                   │
   ServiceRegistry  ◀── reads heartbeats / detects expiry ──┘
   (inside EM)
        │ binds game + defuser + expert manifests
        ▼
     Session ──▶ ExperimentDescriptor ──▶ ExperimentRunner
                 (session_id = uuid)            │
                                                ├─▶ GameClient   ─┐
                                                └─▶ PlayerClient ─┤ RPC over redis
                                                                  ▼  game:{uuid}:commands:*
                                                          GameService /  player:{uuid}:commands:*
                                                          PlayerService
```

- **`service`** — a long-running process that broadcasts a heartbeat to redis and registers RPC
  command handlers. Only `GameService` and `PlayerService` are services. Both combine
  `HeartbeatBroadcaster` with `BaseRPCService`.
  `src/gptnt/interactive/services/heartbeat/broadcaster.py`, `src/gptnt/interactive/services/rpc.py`.
- **`ExperimentManager` (EM)** — the orchestrator. It subclasses `ObservableServiceRegistry`, holds
  the open `ExperimentSpec` set and the live `Session` set, runs the matchmaking loop, and reacts to
  service expiry by force-stopping the affected `Session`. It is not a service: it broadcasts no
  heartbeat and exposes readiness over an HTTP health endpoint.
  `src/gptnt/interactive/services/experiment_manager/experiment_manager.py`.
- **`ServiceRegistry`** — the lower layer. It pulls `heartbeat:*` keys from redis, builds a
  `ServiceManifest` per uuid, marks expired ones, and offers `ready_players` and `ready_games`. It has
  no notion of experiments or sessions. The EM extends it.
  `src/gptnt/interactive/services/registry/registry.py`.
- **`ServiceManifest`** — the EM's record of one connected service: its latest `Heartbeat` plus a
  `ServiceState` (`idle`, `in_experiment`, `cleanup`, `not_ready`). `ServiceState` is the
  orchestration view set by the EM and `Session`, separate from the readiness the service reports in
  its own heartbeat. `is_expired` compares the heartbeat timestamp against the expiration timeout.
  `src/gptnt/interactive/services/registry/manifest.py`.
- **`Heartbeat`** — the liveness message a service writes to redis on a timer. It carries a
  `ReadyState` (`ready` / `not_ready`), the service's domain state (`PlayerState` for players,
  `GameState` for the game), and diagnostic fields (`heartbeat_seq`, `uptime_seconds`, `pid`,
  `hostname`). The key has a TTL, so a missed heartbeat expires the service.
  `src/gptnt/interactive/services/heartbeat/base.py`.
- **`GameService`** (game room) — the service wrapping one KTANE game instance. It handles RPC commands
  such as `configure_game`, `send_action`, `advance_game_time`, `get_bomb_state`, and `get_frames` on
  `game:{uuid}:commands:*`, delegating to the underlying game client.
  `src/gptnt/interactive/services/game/service.py`.
- **`PlayerService`** — the service wrapping one model-backed player. It handles
  `configure_for_experiment`, `forward_pass`, `reflection`, `send_feedback`, and `stop` on
  `player:{uuid}:commands:*`, driving the agent loop and recording steps. A player serves as defuser or
  expert depending on the protocol it is configured with.
  `src/gptnt/interactive/services/player/service.py`.
- **`Session`** — the in-process runtime object the EM creates per experiment. It binds the chosen
  game, defuser, and optional expert manifests with an `ExperimentSpec`, mints `experiment_uuid` (the
  `session_id`), builds the `ExperimentDescriptor`, and constructs the matching `ExperimentRunner`. Its
  lifecycle methods (`run`, `force_stop_experiment`, `cleanup`) flip the bound manifests'
  `ServiceState` and run inside the EM's task group.
  `src/gptnt/interactive/services/experiment_manager/session.py`.
- **`ExperimentRunner`** — owns the experiment lifecycle for one `Session`: configure services,
  synchronize the start, run the step loop, send reflections, then clean up. `SyncExperimentRunner`
  steps one player at a time with the game paused between turns. `AsyncExperimentRunner` runs each
  player in its own loop without pausing. It detects game-over and crashes through heartbeat-driven
  state watchers. `src/gptnt/interactive/services/experiment_manager/experiment_runner.py`.
- **`GameClient` / `PlayerClient`** — the RPC clients the `ExperimentRunner` uses to drive the
  services. Each subclasses `BaseRPCClient`, targets a per-uuid command channel, and sends commands
  with `broker.request(...)`. They are callers, not services.
  `src/gptnt/interactive/services/game/client.py`, `src/gptnt/interactive/services/player/client.py`.
- **`spawn`** — the helper functions that launch the cluster's processes through the orchestrator:
  `spawn_experiment_manager` (then waits on its health endpoint), `spawn_rooms` (game instances), and
  `spawn_players`. Each launches an entrypoint module as a subprocess; the service then self-announces
  by broadcasting heartbeats. `src/gptnt/interactive/orchestration/spawn.py`.
- **`ProcessOrchestrator`** — the process-lifecycle engine. It spawns subprocesses with logging, polls
  their exit codes, reports the first failure, and terminates the cluster (SIGTERM, then SIGKILL) on
  shutdown. It tracks OS processes only. From the EM's view a service is born at its first heartbeat
  and dead at heartbeat expiry, not at process exit.
  `src/gptnt/interactive/orchestration/orchestrator.py`.
- **`redis` / FastStream RPC** — the single transport, with two roles. Discovery: services write TTL'd
  heartbeat hashes under `heartbeat:*`, and the registry scans them to learn who is alive. Control:
  commands travel as FastStream requests over per-uuid channels (`game:{uuid}:commands:{command}`,
  `player:{uuid}:commands:{command}`), with services subscribing and clients calling
  `broker.request(...)`. `src/gptnt/interactive/services/rpc.py`,
  `src/gptnt/interactive/services/heartbeat/broadcaster.py`.

## Record layer — what a result is

Playing one `ExperimentSpec` records one attempt, and no single object is "the result". A result lives
at three grains: the step, the per-player record, and the per-attempt summary. The split that matters
is written versus derived. The recorder writes the durable artifact — one parquet file per player
(`ExperimentPlayerRecord`), each holding that player's `ExperimentStep` rows and a `RecordFooter`.
`gptnt records build-db` later derives the query surface from those files: one `ExperimentSummary` row
per attempt and the `experiment_step` table of every step. The parquet is always written; the DuckDB
tables are rebuilt from it. See `docs/recording-and-ledgers.md` for the write and ingest contract.

```text
recorder (durable, on disk)                  build-db ingest (DuckDB query surface)
─────────────────────────────               ──────────────────────────────────────
one parquet file per player:                 experiment_summary  one ExperimentSummary / attempt
  ExperimentPlayerRecord        ──build-db──▶ experiment_step     every player's ExperimentStep rows
    = ExperimentStep rows
    + RecordFooter
       (descriptor, final_bomb_state,
        is_hard_crash, role, provenance)
```

- **`attempt`** — the unit that is generated, run, and recorded: one `ExperimentSpec`, one physical
  `session`, and the records below. Solo runs have a defuser only. An experiment groups its attempts
  (see the units section).
- **`ExperimentPlayerRecord`** (`experiments.models`) — the durable record of one player's side,
  persisted as a single parquet file (`experiments.recorder`). It holds the player's `ExperimentStep`
  rows and the experiment-level `RecordFooter`. This is what the recorder always writes; everything in
  DuckDB is derived from it.
- **`ExperimentStep`** (`experiments.models`) — one row: a single player step (step index, timestamp,
  role, ids, output, thoughts, `bomb_state`, observation, usage). The rows inside an
  `ExperimentPlayerRecord`, and the `experiment_step` table after ingest.
- **`RecordFooter`** (`experiments.recorder.parquet`) — the experiment-level footer carried in each
  player's parquet: the `ExperimentDescriptor`, the `final_bomb_state`, `is_hard_crash`, `role`, and
  provenance. Identity and grouping come from the footer, never the filename.
- **`ExperimentDescriptor`** (`experiments.descriptor`) — the runtime identity of one experiment: the
  `ExperimentSpec`, the actual `PlayerCapabilities` each player ran with, and the `session_id`, player,
  and game UUIDs. The source of truth for who played, carried verbatim in every `RecordFooter`.
- **`ExperimentRecord`** (`experiments.models`) — the whole-experiment view assembled in memory from
  both players' `ExperimentPlayerRecord`s plus the shared descriptor. It joins the per-player files; it
  is not separately persisted.
- **`ExperimentSummary`** (`experiments.models`) — the derived per-attempt row, one per attempt (keyed
  by `attempt_name`) in the DuckDB `experiment_summary` table. `build-db` builds it from the player
  footers (descriptor, outcome, and provenance taken from the defuser file). The browse, filter, and
  seed index, not a recorded artifact.
- **`ExperimentOutcome`** (`experiments.models`) — the small set of facts about how the bomb ended,
  derived once from the final `BombState`. The DuckDB row and the W&B `run.summary` serialize the same
  object, so the two are interchangeable.
- **`outcome` fields** (`is_solved` / `is_detonated` / `is_timed_out` / `is_strike_out` /
  `is_hard_crash` / `seconds_remaining` / `strike_count` / `num_modules_solved`) — the
  `ExperimentOutcome` fields. `is_valid_outcome` reads four of them to decide a clean run.
- **`final_bomb_state`** — the last observed `BombState` of the run, the source the outcome is derived
  from. Only the defuser observes the bomb, so it lives in the defuser's footer and is `null` in the
  expert's.
- **`session_id`** — the UUID of one physical run of an attempt, the `Session`'s UUID. It groups the
  per-player parquet files of one attempt, and ingest joins steps to their summary on it.
- **`(session_id, role)`** — one player's conversation within a run: exactly one
  `ExperimentPlayerRecord`. Ingest dedupes on `(session_id, player_uuid)`.
- **`ledger`** — what answers "which experiments are already done?". The local ledger reads this
  machine's parquet footers; the W&B ledger queries runs across all machines. Both decide validity
  through `is_valid_outcome`. See `docs/recording-and-ledgers.md`.

## Identity, digests, and comparability

Two recorded results are comparable when they share the same `suite_name`, the same `suite_revision`,
and the same capability fingerprint on each side. A suite names no model and a model names no suite, so
those facts meet only on the recorded result — in each player's `RecordFooter`, and on the derived
`ExperimentSummary` that surfaces the suite identity, the revision, and a fingerprint per role for
queries. Comparability says the two results measure the same thing.
Reproducing a result is a stronger ask: it also needs `gptnt_version` and `git_sha`, the code that
produced the run. The freeze enforces the contract from the other side. `test_frozen_suites` pins each
suite to its `(revision, suite_digest)` pair, so editing the suite config or any mission file it loads
fails the test unless `revision` is bumped. A bumped revision marks a new measurement. Results under
the old revision are not pooled with the new.

```text
                  suite (config, no model)            model (capabilities, no suite)
                  ┌───────────────────────┐           ┌────────────────────────────┐
                  │ config_digest          │          │ PlayerCapabilities          │
                  │ missions_digest        │          │   .fingerprint              │
                  │   ▼ combined           │          └──────────────┬──────────────┘
                  │ suite_digest           │                         │
                  └───────────────────────┘                         │
                              │  pinned by test_frozen_suites        │
                              │  to (revision, suite_digest)         │
                              ▼                                      ▼
                  ┌───────────────────────────────────────────────────────────────┐
                  │ ExperimentSummary  (the only place suite and model meet)        │
                  │                                                                 │
                  │ comparability key =                                             │
                  │   suite_name + suite_revision                                   │
                  │   + defuser_capability_fingerprint                              │
                  │   + expert_capability_fingerprint                               │
                  │                                                                 │
                  │ reproduce += gptnt_version + git_sha                            │
                  └───────────────────────────────────────────────────────────────┘
```

- **`stable_digest`** (`gptnt.common.hashing`) — a short hex digest of any JSON-able payload. It
  serialises with sorted keys, then takes a 16-byte blake2b hash. Deterministic across processes and
  machines, unlike the built-in `hash()`, so it can be written into records and compared between runs.
  Every digest and fingerprint below is built from it.
- **`config_digest`** — a `stable_digest` of a `Suite`'s own config, excluding `name`, `revision`, and
  the digest field itself. It reads no files. It changes when the suite's protocol, matchup,
  modalities, or other config fields change.
- **`missions_digest`** — a `stable_digest` of the resolved mission file contents, read from disk under
  the suite's `missions_path`. The per-mission payloads are sorted by their own digest so ordering does
  not affect the result. It changes when a mission in the set is edited even if the suite config is
  untouched.
- **`suite_digest`** — a `stable_digest` of `[config_digest, missions_digest]`. The full fingerprint of
  what a suite measures, config and missions together. `test_frozen_suites` pins it.
- **`capability_fingerprint`** (`PlayerCapabilities.fingerprint`) — a `stable_digest` of a model's full
  `PlayerCapabilities` dump. It identifies one exact model setup. Capabilities are never compared field
  by field across models. The fingerprint catches the case where the same `player_name` ran under two
  different capability sets, so those runs are kept apart.
- **`defuser_capability_fingerprint` / `expert_capability_fingerprint`** — the two
  `capability_fingerprint` values recorded on `ExperimentSummary`, one per side. The expert fingerprint
  is the empty string when there is no expert (a solo defuser). They are computed fields off
  `defuser_capabilities` and `expert_capabilities`.
- **`comparability key`** — the tuple that decides whether two `ExperimentSummary` rows measure the
  same thing: `suite_name`, `suite_revision`, `defuser_capability_fingerprint`, and
  `expert_capability_fingerprint`. Same key, pooled. Different key, kept apart.
- **`reproduce`** (`ProvenanceMixin`) — re-running a result needs more than the comparability key. It
  needs the code. `ProvenanceMixin` stamps `gptnt_version` (the resolved package version, with a
  `.devN+g<sha>` suffix between releases) and `git_sha` (the commit at record time, with a `-dirty`
  suffix when the tree has uncommitted changes) onto every record that carries provenance, including
  `ExperimentSummary`.
- **the `test_frozen_suites` freeze** — a regression gate. It instantiates every discovered suite and
  asserts each one's `(revision, suite_digest)` against a pinned snapshot. A change to a suite config or
  to any mission file moves `suite_digest` and fails the test. The fix is to bump that suite's
  `revision`, which marks a new measurement rather than silently pooling with the old. A companion test
  holds each suite's `name` to its filename, so a `suites=` reference and the stamped `suite_name`
  cannot drift.
- **the three identity layers** — a recorded run is identified at three grains. The **attempt** is
  `attempt_name`, the logical try as generated. The **execution** is `session_id`, one end-to-end run
  of that attempt. The **conversation** is `(session_id, role)`, one player's side within an execution,
  the grain at which `ExperimentStep` rows and per-role capability fingerprints attach.
