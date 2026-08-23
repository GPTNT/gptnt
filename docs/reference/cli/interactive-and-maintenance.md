---
title: Interactive and maintenance commands
tags:
  - CLI
  - Runtime
  - Results
---

# Interactive and maintenance commands

These commands operate on an existing interactive runtime or its recorded output. The supervised
execution command is documented under [`run`](run.md).

## Queue specifications with `submit`

```text
gptnt submit [--experiment-specs-dir DIRECTORY] [--source SOURCE]
             [--output-dir DIRECTORY] [--dry-run] [--no-filter]
             [--delete-unneeded]
```

| Option | Default and effect |
| ------ | ------------------ |
| `--experiment-specs-dir` | `output/experiment_specs/`, or `EXPERIMENT_SPECS_DIR`. Recursively loads `*.json`. |
| `--source` | `local`. Accepts `local` or `wandb` as the completion source. |
| `--output-dir` | `output/experiment_recorder_outputs/`, or `EXPERIMENT_RECORDER`. Local completion root. |
| `--dry-run` | Logs the remaining specifications without posting them. |
| `--no-filter` | Sends every loaded specification without a completion check. |
| `--delete-unneeded` | Deletes specification files excluded after completion filtering. |

The command posts to `POST /add-specs` on an experiment manager that is already running. It does
not start game or player services and does not monitor them.

!!! danger "Queue `submit` is not submission delivery"
    `gptnt submit` sends experiment specifications to the runtime queue.
    `gptnt submission submit` sends built result bundles to the submissions repository.

## Inspect completion with `status`

```text
gptnt status [SOURCES ...] [--source {local,wandb}] [--output-dir DIRECTORY]
```

`SOURCES` accepts one existing specification directory, one or more suite IDs, or no value. No
value generates expected attempt names for every discovered suite. A directory cannot be mixed
with suite IDs.

The output reports `done`, `failed`, `running`, and `not attempted`. The local ledger reads Parquet
footers. The optional live overlay reads active attempt names from the experiment manager.

## Stop leftover processes with `kill`

```text
gptnt kill
```

The command forcibly terminates Python processes running GPTNT interactive entry points and KTANE
processes. It has no options.

## Preview or remove invalid local outputs

```text
gptnt cleanup-outputs [TARGET] [--execute]
```

`TARGET` defaults to `output/experiment_recorder_outputs/`. The command finds invalid or incomplete
experiment groups and orphaned `experiment-*.parquet.tmp` files. It only previews without
`--execute`.

!!! warning "Inspect the preview"
    `--execute` deletes the listed files. Keep completed source Parquet through submission
    validation.

## Reconcile W&B

```text
gptnt reconcile-wandb [DIRECTORY] [--execute] [--include-dummy-runs]
                      [--mark-missing-output-as-old |
                       --no-mark-missing-output-as-old]
```

The command requires the W&B extra plus `WANDB_ENTITY` and `WANDB_PROJECT`. It tags invalid,
duplicate, or orphaned remote runs as `old`. When `DIRECTORY` is supplied, it can also delete local
files that lack a valid W&B run. It previews by default; `--execute` applies remote and local
changes. Missing local output is marked `old` by default.

[Run interactive experiments](../../running/run-your-model.md){ .md-button }
[Troubleshoot interrupted output](../../troubleshooting/interrupted-runs-and-outputs.md){ .md-button }
