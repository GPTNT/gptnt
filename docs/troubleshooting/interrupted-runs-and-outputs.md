---
title: Interrupted runs and outputs
tags:
  - Runtime
  - Results
---

# Interrupted runs and outputs

Start with the state you can observe, then use the matching check before deleting or resubmitting
anything.

## The terminal stopped but processes remain

Check whether the experiment manager and child processes still appear in the run logs or process
list. If a normal run monitor is still active, let its termination path finish. When shutdown has
failed and the processes are left behind, run:

```bash title="Run in your shell"
gptnt kill
```

`kill` forcibly terminates all matching GPTNT interactive entry points and KTANE processes, not
only one manifest's cluster.

## `status` reports running after the run stopped

`status` overlays queued and running attempt names from `GET /active` when the experiment manager
is reachable. If the manager is stale, stop the leftover cluster and rerun `status`. The local
footer ledger itself reports only `done`, `failed`, and `not attempted`.

## `status` reports failed or not attempted

Point `--output-dir` at the exact recorder directory printed by `run`. `not attempted` means the
ledger found no matching footer group. `failed` means files exist but the group is incomplete,
hard-crashed, or lacks a valid solved, timeout, or strikeout outcome.

Inspect `output/logs/run_<run-output-name>/` for the process that stopped. Correct the runtime or
provider condition, then rerun the manifest. Completion filtering skips valid attempts and queues
the remaining ones.

## A `.parquet.tmp` file remains

The recorder writes `experiment-*.parquet.tmp` before an atomic rename. A remaining temporary file
is not a completed record. Preview cleanup:

```bash title="Run in your shell"
gptnt cleanup-outputs <recorder-directory>
```

Only after checking every listed file, apply it with `--execute`.

!!! warning "Cleanup deletes source evidence"
    `cleanup-outputs --execute` deletes invalid record groups and orphaned temporary writes. Keep
    completed Parquet files through submission validation.

## `build-db` rejects the database schema

The existing database has a v1 or otherwise incompatible base-table structure. Rebuild from the
retained Parquet:

```bash title="Run in your shell"
gptnt build-db <recorder-directory> \
  --output output/experiments.duckdb \
  --delete-existing-db
```

## Static predictions exist without metadata

GPTNT refuses to assign current provenance to older `prediction_*.json` files when `run_meta.json`
is missing. Move the incomplete output directory aside or remove it after preserving anything
needed for diagnosis, then rerun the static task from the beginning.

[Run interactive experiments](../running/run-your-model.md)
[Output layout](../reference/files/output-layout.md)
