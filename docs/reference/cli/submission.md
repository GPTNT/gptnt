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

```text title="Command syntax"
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

```text title="Command syntax"
gptnt submission validate [PATH] [--format {rich,json,github}]
                          [--require-installed-lock-match]
                          [--require-installed-release-match]
```

`PATH` defaults to `output/submissions/` and can identify one bundle or a root containing several.
`--format` defaults to `rich`. Use `json` for machine output and `github` for CI annotations. Failed
checks produce a non-zero exit status, while warnings leave it at zero.

`--require-installed-lock-match` additionally requires each interactive bundle's suite snapshot to
exactly match the suite registry resolved by the GPTNT installation running the command. The option
does not itself verify that installation is a published release. Submissions CI verifies the
declared release before using this option.

`--require-installed-release-match` resolves each bundle's annotated release tag in the installed
source repository. It requires the tag to target the recorded commit and the recomputed release
protected-content digest to match the manifest. This check is independent of
`--require-installed-lock-match`; use both when both identities must match.

## `submission submit`

```text title="Command syntax"
gptnt submission submit [PATH] [--repo OWNER/NAME] [--dry-run]
```

`PATH` defaults to `output/submissions/`. `--repo` defaults to `gptnt/submissions`. `--dry-run`
performs authentication, repository lookup, clone, local branch, staging, and commit work, but it
does not fork, push, or open a pull request.

Each top-level bundle directory becomes one branch, commit, and pull request. Remote operations
need the submission extra and a token from `GITHUB_TOKEN` or `gh auth token`.
