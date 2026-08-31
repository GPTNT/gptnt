---
title: Run manifest
tags:
  - Configuration
---

# Run manifest

A run manifest is a YAML mapping accepted by `gptnt doctor`, `gptnt generate`, and `gptnt run`.
Schema version 2 is the only accepted version. Unknown fields are rejected on the manifest, roster
entries, and anchors.

## Complete example

`runs/quickstart.yaml` is the smallest checked-in manifest that exercises a two-player suite:

```yaml
--8<-- "runs/quickstart.yaml"
```

Use [Create a run manifest](../../run-and-submit/create-run-manifest.md) for the authoring procedure.

## Field effects not conveyed by the schema

| Field | Effect |
| ----- | ------ |
| `rooms` | Number of KTANE game-service processes started for concurrent experiments. |
| `players` | Roster whose `count` values determine how many player-service processes are started. |
| `anchors` | Player configuration names used by `with_best_*` pairings. A used anchor must also resolve from the roster. |
| `observability` | `full` retains configured instrumentation, `limited` keeps Pydantic AI instrumentation with aggressive sampling, and `off` disables instrumentation. |

`displays` assigns room processes to X display numbers in round-robin order. `None` preserves the
ambient `DISPLAY`. `source` selects the local or W&B completion ledger used to filter completed
attempts. `attempts_per_mission` changes generation depth rather than suite identity.

Each `suites` entry accepts `<name>` for the latest frozen revision or `<name>@<revision>` for one
specific frozen revision. `gptnt run` rejects pre-generated specifications whose suite names and
revisions do not match these selectors.

## Manifest fields

::: gptnt.cli.run.manifest.RunManifest
    options:
      members: false

## Roster entries

::: gptnt.players.specification.PlayerSpec
    options:
      members: false

## Anchors

::: gptnt.cli.run.manifest.Anchors
    options:
      members: false

## Completion source

::: gptnt.experiments.ledger.completion.Source
    options:
      members: true
