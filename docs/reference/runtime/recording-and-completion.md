---
title: Recording and completion
tags:
  - Runtime
  - Results
  - Maintainer reference
---

# Recording and completion

This page traces the current implementation from a player call to Parquet, completion state, and
DuckDB ingest. These classes and storage details are maintainer contracts, not supported extension
points.

## Record one player step

`ExperimentPlayerRecorder.configure_for_experiment` binds the runtime instance, role, player UUID,
and one provenance snapshot. Observation building writes a temporary Dill pickle and retains its
path. After model output dispatch starts, `track_step` records the relative timestamp, action,
messages, usage, bomb state, observation path, parsing errors, and reflection state.

Stopping the player builds an `ExperimentPlayerRecord`. The recorder reloads any observation paths,
serialises the step rows using the DuckDB field representation, writes a sibling `.tmp` Parquet
file, and atomically renames it. The recorder does not write Parquet for a player with no steps.

## Finalise an execution

The Parquet footer stores the `ExperimentInstance`, last captured bomb state, player role, hard-
crash state, and provenance. Flat metadata keys expose the format version, session ID, and player
UUID without parsing the complete footer.

Local completion groups footers by the canonical `instance.attempt_name`. `validity_from_footers`
requires the expected player records and the shared valid outcome. The W&B ledger uses the same
outcome rule while reading cross-machine state.

## Ingest into DuckDB

During ingest, record files are grouped by session. Worker processes derive one
`ExperimentSummary` from each footer group, then the transaction merges the source step rows and
derived summaries. A failed group is excluded in full, so ingest does not leave orphan step rows.

An existing database is accepted only when its ordered base-table structure equals the schema
generated from `ExperimentStep` and `ExperimentSummary`. No database version row or view mediates
compatibility.

[Player-record format](../files/player-records-and-outcomes.md)
[DuckDB schema](../files/duckdb.md)
