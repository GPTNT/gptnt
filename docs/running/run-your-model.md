---
title: Run interactive experiments
tags:
  - CLI
  - Runtime
  - Results
---

# Run interactive experiments

Run pre-generated experiment specifications, monitor the service cluster, and retain the player
records needed for analysis and submission.

## Before you start

You need:

- an installation that passes `gptnt doctor`;
- a run manifest whose player roster can satisfy every selected suite;
- experiment specifications generated with `gptnt generate`; and
- every required manual available or downloadable.

Create and validate the run manifest before continuing. For the current schema and generation
command, see [Experiment hierarchy](../understand/experiment-hierarchy.md) and
[`generate`](../reference/cli/generate.md).

!!! warning "Generate before running"
    `gptnt run` does not generate specifications. It always reads
    `output/experiment_specs/<manifest-stem>/`. If you generated into another directory with
    `--output-dir`, move or regenerate the files at the path that `run` reads.

## Check the run plan

Run the complete doctor check against the manifest:

```bash title="Run in your shell"
gptnt doctor runs/<name>.yaml
```

Correct benchmark-integrity and roster failures before continuing. An anchor required by a suite
must resolve through the manifest roster. The roster also needs enough player-service capacity for
the selected protocols and number of rooms.

`--force` can continue past an ordinary doctor failure. It cannot bypass benchmark-integrity,
run-roster, or manual-preparation failures. `--allow-modified-benchmark` is a contributor override
that records `protected_content_modified: true`. Those results cannot be submitted.

## Start the run

```bash title="Run in your shell"
gptnt run runs/<name>.yaml
```

The command performs these operations in order:

1. Load the generated specification JSON files.
2. Run doctor against those exact specifications.
3. Filter attempts already complete under the manifest's completion source.
4. Prepare the manual profiles needed by the remaining attempts.
5. Start the experiment manager, game rooms, and player services.
6. Submit the remaining specifications and monitor the child processes.
7. Terminate the cluster after the work completes or a child fails.

The default terminal view shows process status. Stream prefixed child logs instead with:

```bash title="Run in your shell"
gptnt run runs/<name>.yaml --interactive
```

Both modes retain process logs under `output/logs/run_<run-output-name>/`.

## Confirm completion

A completed monitor prints `Run finished`, followed by the log directory and experiment-output
directory. If every specification is already complete, `run` prints `Nothing to run.` and starts
no processes.

Check an output directory or suite explicitly:

```bash title="Run in your shell"
gptnt status output/experiment_specs/<name> \
  --output-dir output/experiment_recorder_outputs/<timestamp>
```

The `local` completion source groups Parquet footers by attempt name and reports `done`, `failed`,
or `not attempted`. While an experiment manager is reachable, `status` overlays queued and running
attempts. A manifest with `source: wandb` uses the W&B ledger instead.

!!! warning "Retain the Parquet records"
    DuckDB and submission bundles are derived from player-record Parquet. Keep the source files
    until every intended bundle passes submission validation.

## Use an existing experiment manager

The top-level `gptnt submit` command sends specification files to an experiment manager that is
already running. It does not start services or monitor them. This queue command is different from
`gptnt submission submit`, which opens pull requests for validated result bundles.

Use the supervised `run` command for the normal workflow. See
[Interactive and maintenance commands](../reference/cli/interactive-and-maintenance.md) for the
queue, status, termination, and cleanup interfaces.

## Continue

[Inspect and analyse results](inspect-results.md)
[Troubleshoot an interrupted run](../troubleshooting/interrupted-runs-and-outputs.md)
