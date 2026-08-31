---
title: Manual commands
tags:
  - CLI
---

# Manual commands

The `manual` command group prepares manual sources and compiled artefacts without starting an
experiment run.

## `gptnt manual download`

Download the remote inputs for the selected manual profiles into `output/manual_cache/sources/`.
The command does not resolve or compile a handbook.

```text title="Command syntax"
gptnt manual download [--suite SUITE]... [--all-profiles]
```

| Option | Accepted value | Meaning |
| ------ | -------------- | ------- |
| `--suite` | Suite configuration name; repeatable | Select profiles used by each suite argument. Repeated suites and shared profiles are deduplicated in first-seen order. |
| `--all-profiles` | Flag | Select every non-private profile under `configs/manual/`. |

`--suite` and `--all-profiles` are mutually exclusive. With neither option, the command selects
profiles used by all configured suites.

## `gptnt manual compile`

Run the complete download, resolution, and compilation pipeline for the selected suites.

```text title="Command syntax"
gptnt manual compile [--suite SUITE]...
```

With no `--suite`, the command selects every configured suite. It deduplicates matching
profile-and-rule-seed requirements, so two suites using one profile with different
`manual_rule_seed` values compile separate artifacts. A successful compile writes or reuses a
validated content-addressed directory under `output/manual_cache/artifacts/`.

An explicit `<name>@<revision>` selector compiles the manual requirement stored with that frozen
suite revision. An unpinned name uses the configured suite.

HTML compilation requires the Playwright-managed Chromium version installed for the current Python
environment. Profiles made only from selected pages of official PDF manuals do not use Chromium.

## Failure boundary

Selection rejects an unknown suite or an empty suite set. Download reports missing remote data.
Resolution names the profile entry or frontmatter that cannot be resolved. Compilation reports
browser, HTML, PDF, or artefact validation failures.

The CLI prints the failure and exits nonzero. It does not start runtime services.

Use [Prepare manuals](../../run-and-submit/prepare-manuals.md) for the workflow and
[manual preparation troubleshooting](../../troubleshooting/manual-preparation.md) for corrective
steps.
