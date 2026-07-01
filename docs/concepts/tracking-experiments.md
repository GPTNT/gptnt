# Tracking experiments

!!! danger
A lot of this was drafted by the magic box and is not in it's final form. It needs to be redone basically.

This explains what happens when an experiment runs: what gets written, where, and how the system
later answers two questions — _"what was the outcome?"_ and _"which experiments are already done so I
can skip them on a re-run?"_

The whole design rests on one idea: **local disk is the durable spine; Weights & Biases (W&B) is an
optional, additive mirror and a cross-machine aggregator.** Nothing is W&B-only.

---

## Two independent axes

W&B and local are **not** an either/or choice. They are two separate axes, and the W&B side of each
is _additive_ — it never replaces the local side.

| Axis         | Question it answers                | Local                     | W&B                                 |
| ------------ | ---------------------------------- | ------------------------- | ----------------------------------- |
| **Recorder** | "how is this experiment saved?"    | parquet file on disk      | local **+** live cloud mirror       |
| **Ledger**   | "which of these are already done?" | reads this machine's disk | reads the union across all machines |

---

## Axis 1 — Recorder: how an experiment is saved

An experiment has **one player (solo defuser)** or **two players (defuser + expert)**. The recorder
writes **one parquet file per player**:

```
            ONE EXPERIMENT  (session_id = S)
            │
   ┌────────┴───────────┐
   ▼                    ▼
experiment-{name}-{defuser_uuid}.parquet     experiment-{name}-{expert_uuid}.parquet
                                             (only if there is an expert)
```

### What one player file contains

```
┌─ experiment-{name}-{player_uuid}.parquet ─────────────────────────────────────┐
│                                                                                │
│  ROWS   = this player's steps (one row per step, in the DuckDB-ready form)     │
│           step · timestamp · role · session_id · player_uuid · player_name     │
│           output · raw_output · thoughts · input_messages⋆ · new_messages⋆     │
│           bomb_state(json) · observation⋆ · usage⋆ · num_prompt_truncations    │
│           error_type[] · is_reflection            ⋆ = zstd+msgpack large_binary │
│                                                                                │
│  FOOTER = one validated `RecordFooter` (JSON) + a few flat scalar keys         │
│           RecordFooter = { descriptor, final_bomb_state, is_hard_crash, role,  │
│                            provenance (version/edition/git_sha) }              │
│           flat keys: session_id · player_uuid · format_version                 │
└────────────────────────────────────────────────────────────────────────────────┘
```

The footer holds the experiment-level facts (the inputs in `descriptor`, the outcome in
`final_bomb_state`, the crash flag, the provenance). The rows are the steps. The single read/write
contract is `experiments/recorder/parquet.py`.

> **The outcome lives only in the defuser's file.** Only the defuser observes the bomb, so
> `final_bomb_state` is present in the defuser's footer and `null` in the expert's. The two files are
> not stitched together on disk — they are joined later, at ingest, by `session_id`.

### Local recorder vs W&B recorder

```
   LOCAL recorder                       WANDB recorder  =  LOCAL recorder  +  live cloud mirror
   ───────────────                      ──────────────────────────────────────────────────────────
   track_step ─┐                        track_step ─┬──────────────► wandb.log(step)        (live)
               ▼                                     │
   on_stop:                             on_stop ─────┼──► write parquet to disk  ◄── SAME contract
     write parquet to disk                          └──► wandb.log(summary + step table)   (cloud)
```

`WandbExperimentPlayerRecorder` **extends** `ExperimentPlayerRecorder` (`recorder/wandb.py`). It does
everything the local recorder does — **including writing the parquet to disk** — and additionally
logs each step live and a final summary + step table to W&B.

**Consequence:** the parquet on disk is always written, whichever recorder runs. So the local DuckDB
can always be rebuilt on any machine, and W&B is never the only copy of anything.

---

## The outcome vocabulary (one source of truth)

The experiment _outcome_ is the small set of facts about how the bomb ended. It is computed **once**
from the authoritative `BombState` into a single `ExperimentOutcome` object
(`experiments/models.py`), and both stores carry the **same field names and values**:

| field                | meaning                                              |
| -------------------- | ---------------------------------------------------- |
| `is_solved`          | bomb defused                                         |
| `is_detonated`       | bomb exploded                                        |
| `is_timed_out`       | detonated because the timer hit zero                 |
| `is_strike_out`      | detonated because of too many strikes                |
| `is_hard_crash`      | the run crashed (infra/code), not a real game ending |
| `seconds_remaining`  | time left on the timer at the end                    |
| `strike_count`       | strikes accrued                                      |
| `num_modules_solved` | modules defused                                      |

`ExperimentOutcome.from_bomb_state(bomb_state, is_hard_crash=...)` is the only place these are
derived — every field reads straight off a `BombState` property (no re-derivation, no magic numbers).
The DuckDB `experiment_summary` row and the W&B `run.summary` both serialize this same object, so the
two sources are interchangeable: a query reads the same names whether it hits the DB or W&B.

---

## Axis 2 — Ledger: "which experiments are already done?"

Before a run, the supervisor asks a **ledger** which of the planned experiments are already finished,
so it can skip them. This is the one piece that genuinely swaps, via `--source local|wandb`
(`experiments/ledger/`). Both implementations satisfy the same `CompletionLedger` protocol
(`status_for`, `completed`) and **must agree** on what "done & valid" means.

```
   LOCAL ledger  (one machine / one shared disk)      WANDB ledger  (multi-machine AGGREGATOR)
   ─────────────────────────────────────────────     ──────────────────────────────────────────
   glob this machine's experiment-*.parquet           query W&B runs by attempt_name
      group by footer session_id                         (sees EVERY machine on the same project)
      is the group a valid, completed experiment? ──┐    is each run valid? ──┐
                                                     ▼                         ▼
   sees ONLY this disk            ───────────────►  done set  ◄───────────  sees the UNION of machines
```

Reach for the **W&B ledger only for multi-machine work** — when experiments are spread across many
machines and no single disk sees them all, W&B is the aggregator that knows the union. On a single
machine (or one shared disk), the **local ledger** reading the parquet the recorder always wrote is
enough.

### One definition of "valid / done"

Both ledgers decide validity through the **same** function, `is_valid_outcome`, which reads only the
four flags that decide it (`is_solved`, `is_timed_out`, `is_strike_out`, `is_hard_crash`) — so
neither side has to reconstruct a full `ExperimentOutcome` just to ask:

```python
valid = (not is_hard_crash) and (
    (is_solved and not is_timed_out and not is_strike_out)      # a clean solve
    or (not is_solved and (is_timed_out or is_strike_out))      # a clean, real failure
)
```

- **Local** reads the four flags off the footer's `final_bomb_state` (`validity_from_footers` →
  `is_valid_experiment`, `experiments/db/_extract.py` and `models.py`).
- **W&B** reads them straight off `run.summary` (after a transport guard that the run is `finished`
  and the metric keys are present), in `is_run_valid` (`experiments/wandb_runs.py`). These four
  flag names never drifted, so the reader needs no legacy-name fallback.

Because both feed one function over one vocabulary, "already done" cannot silently depend on
`--source`.

> **`WandbLedger.completed()` also prunes.** Unlike the pure-read local ledger, the W&B ledger marks
> stale/invalid remote runs as `old` while answering, so a run left in a bad state does not block a
> re-run. This remote side-effect is intentional (resume hygiene) and is the one place the two
> ledgers differ in _behaviour_ (not in their definition of valid).

---

## From disk to the query surface (`gptnt records build-db`)

The local ledger needs no database — it reads footers directly. The **app and the future seeder**
query DuckDB, which `build-db` rebuilds from the parquet files:

```
build-db  rglob("experiment-*.parquet")
   └─ ingest (experiments/db/ingest.py)
        ├─ filter out experiments already in the DB   (dedupe on footer (session_id, player_uuid))
        ├─ group the player files by footer session_id
        ├─ per experiment → build one ExperimentSummary from the footers
        │        descriptor / outcome / provenance  ← the defuser file (canonical)
        │        is_hard_crash                       ← OR across the experiment's files
        │        mission_key                         ← hash(sorted(modules), seed)
        └─ one transaction:
               INSERT experiment_summary  ◄── the in-memory summaries  (1 row / experiment)
               INSERT experiment_step     ◄── read_parquet(recorder files)  (N rows / experiment)
```

Two tables result:

- `experiment_summary` — one row per experiment (the browse/filter/seed index).
- `experiment_step` — every player's steps, joined to the summary on `session_id`.

Identity and grouping come from the **footer**, never the filename, so renaming a file changes
nothing.

---

## Who reads what

| consumer             | reads                                                                       | via          |
| -------------------- | --------------------------------------------------------------------------- | ------------ |
| **ledger / cleanup** | footers only (outcome + crash flag)                                         | no DB needed |
| **Streamlit app**    | `experiment_summary` to browse, then `experiment_step` for the selected one | DuckDB       |
| **seeder (future)**  | `experiment_summary` filtered by `mission_key`, then its steps              | DuckDB       |

---

## One-line summary

Every experiment is always written to local parquet (W&B is an extra mirror); the outcome is derived
once into a shared `ExperimentOutcome`; and both ledgers answer "already done?" through one validity
function over that one vocabulary — so local and W&B stay interchangeable, with W&B's only unique job
being cross-machine aggregation.
