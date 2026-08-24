---
title: Inspect and analyse results
tags:
  - CLI
  - Results
---

# Inspect and analyse results

Check completion, build a queryable DuckDB database, inspect outcomes and timing, and decide whether
interactive and static outputs are ready for submission.

## Check interactive completion

Use the generated specification directory so `status` checks the exact attempt names from the run:

```bash title="Run in your shell"
gptnt status output/experiment_specs/<manifest-stem> \
  --output-dir output/experiment_recorder_outputs/<timestamp>
```

`done` means the grouped player records have a valid terminal outcome: solved, timeout, or
strikeout, with no hard crash. `failed` means records exist but do not meet that condition.
`not attempted` means no record group exists. A reachable experiment manager can add `running`.

## Build DuckDB

Use the experiment-output directory printed by `gptnt run`:

```bash title="Run in your shell"
gptnt build-db output/experiment_recorder_outputs/<timestamp> \
  --output output/experiments.duckdb
```

The command imports `experiment-*.parquet`, derives one summary per execution from the footers, and
writes the `experiment_step` and `experiment_summary` base tables. It skips sessions already in a
compatible database unless `--skip-filtering` is set.

!!! warning "DuckDB is derived data"
    Do not remove the source Parquet after building DuckDB. Keep it through bundle construction
    and successful submission validation.

If an existing database has a v1 or otherwise incompatible structure, rebuild it explicitly:

```bash title="Run in your shell"
gptnt build-db <outputs-dir> --delete-existing-db
```

## Read the results

Render the completed outcomes:

```bash title="Run in your shell"
gptnt results output/experiments.duckdb
```

The table identifies solved, strikeout, and timeout results. Invalid summaries appear in its
caption rather than the ranked rows.

Open the Streamlit analysis application with:

```bash title="Run in your shell"
gptnt analyse
```

The application reads the configured DuckDB database. For direct queries, see the exact
[DuckDB schema](../reference/files/duckdb.md).

## Inspect timing when enabled

If `OBSERVABILITY_CAPTURE_SPAN_TIMINGS=1` was set for the run, summarise the JSONL files beside the
player records:

```bash title="Run in your shell"
gptnt timing output/experiment_recorder_outputs/<timestamp>
```

The report separates Pydantic AI chat-span time from the remaining player-forward-pass time. A run
without `span_timings/*.jsonl` has no timing report.

## Check static outputs

For each static target, confirm that its model directory contains `run_meta.json`, every expected
`prediction_<index>.json`, and `metrics.json`. The metadata must identify the intended player and a
resolved dataset revision for reproducible comparison.

When the required interactive suites and `expert-vqa-no-manual` output are complete, continue to
[Submit your results](submit-results.md).
