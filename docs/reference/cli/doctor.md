---
title: doctor
tags:
  - CLI
---

# `doctor`

`gptnt doctor` checks benchmark integrity and player configuration. It can also check a run plan,
runtime infrastructure, the KTANE mod, or one provider request per configured model.

## Usage

```text title="Command syntax"
gptnt doctor [MANIFEST] [--check-mod-load] [--live] [--config-only]
             [--allow-modified-benchmark]
```

| Input | Required | Effect |
| ----- | -------- | ------ |
| `MANIFEST` | No | Restricts player checks to the manifest roster and adds roster, generated-plan, and resume checks. Without it, doctor checks every discovered player configuration. |

## Options

| Option | Effect |
| ------ | ------ |
| `--config-only` | Checks benchmark integrity, players, image-token settings, and an optional run plan. Skips Redis, KTANE, display, local-service, and machine checks. |
| `--check-mod-load` | Starts bare KTANE and polls the mod `/health` endpoint. The check can take up to 45 seconds and runs only when binary, mod, and display prerequisites pass. |
| `--live` | Sends one provider request per configured model after composition and instantiation. This can incur provider charges. |
| `--allow-modified-benchmark` | Allows a contributor run with modified protected content when that override is available. The resulting provenance is marked modified and is not eligible for submission. |

## Select a mode

| Need | Command |
| ---- | ------- |
| Check all discovered configuration without local services | `gptnt doctor --config-only` |
| Check one manifest without local services | `gptnt doctor runs/<name>.yaml --config-only` |
| Check one manifest and the complete machine | `gptnt doctor runs/<name>.yaml` |
| Confirm that the installed mod responds | `gptnt doctor runs/<name>.yaml --check-mod-load` |
| Confirm provider endpoints with one request per model | `gptnt doctor runs/<name>.yaml --live` |

## Report sections

The report renders only sections that apply to the selected mode.

| Section | What it checks |
| ------- | -------------- |
| Benchmark | Release tag, release commit, and protected-content comparison |
| Players | Configuration composition, object construction, and optional provider request |
| Image tokens | Whether the player has a usable image-token value |
| Run plan | Roster coverage, generated specification count, and completion state |
| Infrastructure | Redis, KTANE binary, mod files, Linux display, experiment-manager port, optional telemetry, and optional mod load |
| Machine | Machine and disk conditions used by the benchmark |

!!! example "Benchmark section"
    The values depend on the installed release. A matching checkout has this form:

    ```text title="Expected output"
    Benchmark
    Reference          v2.0.0
    Release commit     abc1234
    Protected content  matches
    ```

## Success and failure

!!! success "Successful check"
    The command exits without a failing row. It does not print a separate final success sentence.

!!! failure "Doctor found problems"
    A fatal row makes the command raise `Doctor found problems; fix the rows above.` Use the row's
    hint before repeating the command. `--force` belongs to `gptnt run`. It is not a doctor option.

Benchmark-integrity and run-roster failures stop generation and execution before they write
specifications or start processes. Use
[installation and doctor troubleshooting](../../troubleshooting/installation-and-doctor.md) for
configuration or integrity failures. Use the game or Redis troubleshooting page for a row from
that subsystem.
