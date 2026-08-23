---
title: Run the quickstart
tags:
  - CLI
  - Results
---

# Run the quickstart

Run the included `runs/quickstart.yaml` manifest from validation through a queryable result. The
quickstart uses packaged test players and the `single-pairwise-sync` suite. It exercises KTANE,
the runtime services, recording, and database construction without provider credentials.

## Before you begin

Complete [Install and check GPTNT](../get-started.md). The full doctor report must reach Redis and
locate KTANE with its mod. On Linux, it must also use a display.

!!! example "Complete quickstart sequence"
    Run these commands from the repository root. The commands are separate because generation is
    an inspectable step and `run` consumes the specifications already on disk.

    ```bash title="Run the quickstart"
    gptnt doctor runs/quickstart.yaml
    gptnt generate runs/quickstart.yaml
    gptnt run runs/quickstart.yaml
    gptnt build-db <outputs-dir>
    gptnt results
    ```

## Check the run plan

```bash title="Check prerequisites"
gptnt doctor runs/quickstart.yaml
```

The command checks the complete machine and cross-checks the manifest roster against the selected
suite. It exits without a failing row when the run can proceed.

!!! success "Doctor completed"
    The report includes the selected players and a run-plan section. Infrastructure and machine
    sections appear during the full check.

Use the [`doctor` reference](../reference/cli/doctor.md){data-preview} to interpret a row. Follow
[installation](../troubleshooting/installation-and-doctor.md),
[game](../troubleshooting/game-and-displays.md), or
[runtime](../troubleshooting/redis-and-runtime-services.md) troubleshooting for a failed subsystem.

## Generate experiment specifications

```bash title="Generate specifications"
gptnt generate runs/quickstart.yaml
```

`generate` performs the configuration and integrity checks without requiring runtime services. It
writes one JSON file for each mission, pairing, and attempt under:

```text title="Specification directory"
output/experiment_specs/quickstart/
```

!!! success "Specifications were written"
    The final line has this form:

    ```text title="Expected output"
    Wrote <count> spec(s) to output/experiment_specs/quickstart
    ```

The [`generate` reference](../reference/cli/generate.md) describes output overrides and integrity
conditions.

## Run the experiments

```bash title="Run the interactive experiment"
gptnt run runs/quickstart.yaml
```

`run` loads the generated JSON files and repeats the full doctor gate. It filters completed
attempts and prepares the required manual. It then starts the experiment manager, game rooms, and
players before submitting the specifications and monitoring every child process.

The included players exercise the system. They do not guarantee a solved bomb. A completed attempt
can end as solved, strikeout, or timeout.

!!! success "The run finished"
    Before execution, the command prints the log directory and experiment-output directory. After
    queueing, it prints `Specs submitted.` The final block starts with `Run finished` and repeats
    both directories.

Use `gptnt run runs/quickstart.yaml -i` when you need child logs streamed to the terminal. The same
logs remain under `output/logs/run_<run-output-name>/`.

## Build the results database

Copy the experiment-output directory printed by `run`. It normally resembles
`output/experiment_recorder_outputs/<timestamp>/`.

```bash title="Build the result database"
gptnt build-db <outputs-dir>
```

`build-db` reads the `experiment-*.parquet` player records and writes
`output/experiments.duckdb` by default.

!!! warning "Keep the Parquet records"
    DuckDB is a derived local database. Keep the source Parquet files for later validation and
    submission work.

## Inspect an outcome

```bash title="Open the results dashboard"
gptnt results
```

!!! success "The result is queryable"
    The command renders a table titled `KTANE experiment outcomes`. The quickstart row can report a
    solved, strikeout, or timeout outcome.

The artefacts now form this sequence:

```text title="Quickstart artefacts"
runs/quickstart.yaml
  → output/experiment_specs/quickstart/*.json
  → output/experiment_recorder_outputs/<timestamp>/experiment-*.parquet
  → output/experiments.duckdb
  → gptnt results
```

<!-- vale ai-tells.DoubleHyphen = NO -->
[Choose the next workflow](choose-next-workflow.md)
[Understand the experiment hierarchy](../understand/experiment-hierarchy.md)
<!-- vale ai-tells.DoubleHyphen = YES -->
