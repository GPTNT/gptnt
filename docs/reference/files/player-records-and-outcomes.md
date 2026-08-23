---
title: Player records and outcomes
tags:
  - Results
---

# Player records and outcomes

Interactive execution writes one player-record Parquet file per role and session. Player-record
format version **3** is the current contract. Format version 2 belongs to v1 tooling and is rejected.

## Filename and atomic write

The recorder writes:

```text
experiment-<attempt-name>-<player-uuid>.parquet
```

It first writes a sibling `<filename>.tmp`, then atomically renames it. A remaining
`.parquet.tmp` file is an interrupted write and is not completion evidence. The recorder does not
write a file for a player with no step rows.

## Step rows

::: gptnt.experiments.models.ExperimentStep
    options:
      show_root_heading: true

`step` is one-based within one player's record, and reflection rows increment it. `timestamp` is
seconds from the shared experiment start to output dispatch. `session_id` joins roles from the
same execution. Before final Parquet writing, an observation path is replaced with the loaded
observation object.

`output` is the parsed action dispatched for the step. `raw_output` retains an unparsed model
response when available, and `thoughts` holds separately extracted reasoning. Message fields,
observations, and usage use compressed BLOB columns in Parquet and DuckDB.

## Footer

Parquet key-value metadata contains:

| Key | Value |
| --- | ----- |
| `format_version` | ASCII `3`. |
| `session_id` | Execution UUID, repeated as a flat lookup key. |
| `player_uuid` | Player-service UUID, repeated as a flat lookup key. |
| `footer` | JSON encoding of `RecordFooter`. |

::: gptnt.experiments.recorder.parquet.RecordFooter
    options:
      show_root_heading: true

The footer's instance supplies execution identity shared across both player records. Its role says
which player's rows the file holds. `final_bomb_state` is the last state captured for the
execution. It can be null after an early failure.

## Outcomes and summaries

::: gptnt.experiments.models.ExperimentOutcome
    options:
      show_root_heading: true

::: gptnt.experiments.models.ExperimentSummary
    options:
      show_root_heading: true

A valid completed result has `is_hard_crash: false` and an outcome of `solved`, `timeout`, or
`strikeout`. `seconds_remaining` is stored in DuckDB under the alias `timer_seconds`. The summary
adds the runtime instance, suite, mission, protocols, capabilities, outcome, crash state, and
provenance, plus computed fields used for querying.

!!! warning "Retain source records"
    DuckDB summaries and submission `experiments.parquet` are derived from these files. Keep the
    player records until submission validation succeeds.

[Understand results](../../understand/results-and-provenance.md){ .md-button }
[DuckDB schema](duckdb.md){ .md-button }
