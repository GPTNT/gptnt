---
title: Submission commands
tags:
  - CLI
  - Submission
---

# Submission commands

The `submission` command group builds and validates result bundles, then sends them to a repository.
It is separate from the top-level runtime queue command `gptnt submit`.

## `submission new`

```text
gptnt submission new [EXPERIMENTS-DB] [STATICS-OUTPUT-DIR] [OUTPUT-DIR]
                     [--suite NAME ...] [--static TASK ...]
                     [--model NAME ...]
                     [--submitter.name TEXT]
                     [--submitter.contact TEXT]
                     [--submitter.affiliation TEXT]
```

| Input or option | Default and effect |
| --------------- | ------------------ |
| `EXPERIMENTS-DB`, `--experiments-db` | `output/experiments.duckdb`, or `EXPERIMENTS_DB`. |
| `STATICS-OUTPUT-DIR`, `--statics-output-dir` | `output/`, or `STATICS_OUTPUTS`. Contains `<task>_predictions/<model>/`. |
| `OUTPUT-DIR`, `--output-dir` | `output/submissions/`, or `SUBMISSIONS_DIR`. |
| `--suite` | Repeatable. Defaults to `multi-self-async`, `multi-self-sync`, and `single-parametric-sync`. |
| `--static` | Repeatable and empty by default. |
| `--model` | Repeatable player-name filter. All models are present by default. |
| `--submitter.name` | Required for successful validation, but blank is allowed while building. |
| `--submitter.contact` | GitHub handle or email. Required for successful validation. |
| `--submitter.affiliation` | Optional affiliation. |

The aggregate submitter option also declares `SUBMITTER`. The builder requires an unmodified
protected benchmark and a player identity for every bundle it creates.

## `submission validate`

```text
gptnt submission validate [PATH] [--format {rich,json,github}]
```

`PATH` defaults to `output/submissions/` and can identify one bundle or a root containing several.
`--format` defaults to `rich`. Use `json` for machine output and `github` for CI annotations. Failed
checks produce a non-zero exit status, while warnings leave it at zero.

## `submission submit`

```text
gptnt submission submit [PATH] [--repo OWNER/NAME] [--dry-run]
```

`PATH` defaults to `output/submissions/`. `--repo` defaults to `gptnt/submissions`. `--dry-run`
performs authentication, repository lookup, clone, local branch, staging, and commit work, but it
does not fork, push, or open a pull request.

Each top-level bundle directory becomes one branch, commit, and pull request. Remote operations
need the submission extra and a token from `GITHUB_TOKEN` or `gh auth token`.

[Submission procedure](../../submit-your-results.md){ .md-button }
[Bundle schema](../files/submission-bundles.md){ .md-button }
