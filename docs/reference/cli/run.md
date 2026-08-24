---
title: run, submit, and kill
tags:
  - CLI
  - Runtime
---

# `run`, `submit`, and `kill`

`run` supervises an interactive cluster from validation through process termination. `submit`
queues specifications into an experiment manager that is already running. `kill` forcibly removes
matching GPTNT and KTANE processes after normal shutdown is unavailable.

## `run`

```text title="Command syntax"
gptnt run MANIFEST [--force] [--allow-modified-benchmark]
                   [--interactive | -i]
```

| Input or option | Required | Effect |
| --------------- | -------- | ------ |
| `MANIFEST` | Yes | Loads the run manifest and pre-generated specifications from the matching manifest-stem directory. |
| `--force` | No | Continues after ordinary doctor failures. It cannot bypass benchmark-integrity, run-roster, or manual-preparation failures. |
| `--allow-modified-benchmark` | No | Uses the contributor integrity override when available and marks protected content as modified. |
| `--interactive`, `-i` | No | Streams prefixed child logs to the terminal while retaining the log files. The default renders a process-status table. |

!!! warning "Generate first"
    `run` does not generate specifications. It reads
    `output/experiment_specs/<manifest-stem>/`, even when a preceding `generate` command used an
    unrelated output override.

The run order is:

1. Load the generated JSON files.
2. Run full doctor checks against those files.
3. enforce protected-benchmark and roster conditions;
4. filter attempts already complete under the manifest's completion source;
5. prepare only the manual profiles required by remaining attempts;
6. resolve one recorder directory and one log directory;
7. start the experiment manager and wait for `GET /health`;
8. start game rooms and player services;
9. submit the remaining specifications;
10. monitor child processes and terminate the cluster.

If every specification is already complete, the command prints `Nothing to run.` and starts no
process. A missing or empty specification directory stops before doctor or process startup.

### Output and termination

The default recorder directory is a new timestamp under
`output/experiment_recorder_outputs/`. Set `EXPERIMENT_RECORDER_OUTPUTS` to pin one directory. Run
logs use `output/logs/run_<run-output-name>/`.

After submission, the command prints `Specs submitted.` A completed monitor prints `Run finished`,
then the log and experiment-output directories.

A failed child process or failed specification submission terminates the cluster and exits with an
error. Normal termination sends a termination signal, waits up to 35 seconds, and forcibly stops
stragglers.

## `submit`

```text title="Command syntax"
gptnt submit [--experiment-specs-dir DIRECTORY] [--source SOURCE]
             [--output-dir DIRECTORY] [--dry-run] [--no-filter]
             [--delete-unneeded]
```

| Option | Default and effect |
| ------ | ------------------ |
| `--experiment-specs-dir` | Defaults to `output/experiment_specs/`. Recursively loads every `*.json`. Also reads `EXPERIMENT_SPECS_DIR`. |
| `--source` | Defaults to `local`. Completion source is `local` or `wandb`. |
| `--output-dir` | Defaults to `output/experiment_recorder_outputs/`. Supplies the local completion root. Also reads `EXPERIMENT_RECORDER`. |
| `--dry-run` | Logs the specifications that would be sent without posting them. |
| `--no-filter` | Skips the completion check and sends every loaded specification. |
| `--delete-unneeded` | Deletes specification files excluded from the remaining set. |

`submit` posts the remaining specifications to `POST /add-specs` on the configured experiment
manager. It does not start or monitor services.

!!! danger "`--delete-unneeded` changes the specification directory"
    Preview with `--dry-run` and inspect the selected completion source before deleting files.

## `kill`

```text title="Command syntax"
gptnt kill
```

`kill` scans the machine for Python processes running GPTNT interactive entry points and for KTANE
processes, then forcibly terminates each match. It prints the matched process type and PID.

!!! danger "Use forced cleanup only for leftover processes"
    A normal `run` terminates its own process cluster. Use `kill` after a failed or interrupted
    shutdown. Inspect the process list before assuming that each match belongs to the interrupted
    run.
