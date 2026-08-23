---
title: Results and analysis commands
tags:
  - CLI
  - Results
---

# Results and analysis commands

These commands derive and inspect local interactive results. None replaces the source player-record
Parquet.

## `build-db`

```text title="Command syntax"
gptnt build-db DIRECTORY [--output PATH] [--max-workers N]
                         [--skip-filtering] [--delete-existing-db]
```

| Input or option | Default and effect |
| --------------- | ------------------ |
| `DIRECTORY` | Required recorder directory containing `experiment-*.parquet`. Also reads `EXPERIMENT_RECORDER`. |
| `--output`, `-o` | `output/experiments.duckdb`, or `EXPERIMENTS_DB`. |
| `--max-workers`, `-j` | CPU count. Controls the workers that read footer groups. |
| `--skip-filtering` | Does not remove sessions already present before ingest. |
| `--delete-existing-db` | Deletes the selected database and its transient WAL before rebuilding. |

The top-level help currently says JSON, but the implemented input is Parquet. Ingestion requires an
exactly compatible database structure and inserts the step and summary rows in one transaction.

## `results`

```text title="Command syntax"
gptnt results [DB-PATH]
```

`DB-PATH` defaults to `output/experiments.duckdb` and is also accepted as `--db-path`. The command
lists valid completed outcomes and names invalid attempts in the table caption.

## `analyse`

```text title="Command syntax"
gptnt analyse
```

This command starts the Streamlit analysis application. It has no command-line parameters.

## `timing`

```text title="Command syntax"
gptnt timing RUN-DIR
```

`RUN-DIR` must contain `span_timings/*.jsonl`. The report includes information about the machine,
player forward-pass timing, Pydantic AI inference time, framework time, and aggregate span phases.

[Inspect and analyse results](../../running/inspect-results.md)
[DuckDB schema](../files/duckdb.md)
