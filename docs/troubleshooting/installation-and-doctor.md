---
title: Installation and doctor troubleshooting
tags:
  - CLI
  - Configuration
---

# Installation and doctor troubleshooting

Use the narrowest doctor mode that reproduces the failure. Correct its failing row before adding
infrastructure, game startup, or provider requests to the check.

## The release reference is missing

!!! failure "Doctor cannot identify an exact benchmark reference"
    Check that you extracted the complete release directory and kept its bundled `.git` metadata.
    A source archive assembled outside the release workflow may not contain the annotated tag and
    protected-content baseline required by the integrity check.

Run:

```bash title="Check the installation"
gptnt doctor --config-only
```

Use a published release archive for benchmark work. Use a repository checkout only for
contribution and development.

## Protected content differs

!!! failure "Protected content does not match the release commit"
    Restore the named protected source, prompt, manual, or base-configuration files from the
    selected release. Player profiles, permitted suite or mission inputs, and run manifests are
    reported separately when they are allowed runner inputs.

`--allow-modified-benchmark` is a contributor override. When available, it marks provenance as
modified and produces records that cannot be submitted. It is not a way to make changed benchmark
content comparable with the release.

## Dependency installation is incomplete

Repeat the repository tasks from the extracted `gptnt/` root:

```bash title="Install dependencies"
mise install
mise run sync
gptnt doctor --config-only
```

`mise run sync` installs all groups and extras and Playwright Chromium. A direct environment that
omits the browser can pass some configuration checks but later fail manual preparation.

## A player configuration does not compose

Run doctor with the manifest that selects the player:

```bash title="Validate the run configuration"
gptnt doctor runs/<name>.yaml --config-only
```

The player report distinguishes discovery, Hydra composition, object construction, image-token
settings, and optional live requests. Correct the first failing stage. Without a manifest, doctor
checks every discovered player and can report an unrelated profile.

## The run roster does not cover generated work

!!! failure "The selected suites require a missing player"
    Add the player or anchor shown in the report to the manifest roster, or select suites
    compatible with the roster. `--force` cannot bypass this condition because the queue would
    wait for a player that never starts.

Re-run the manifest check before generation:

```bash title="Repeat the configuration check"
gptnt doctor runs/<name>.yaml --config-only
```

Roster capacity depends on the suite protocols. Pairwise work needs both roles. A solo suite does
not use the same two-player assumption.

## The experiment-manager port is occupied

Doctor distinguishes a healthy GPTNT manager from another listener on the configured host and
port. Check which run started the service. If a prior GPTNT cluster failed to stop, use the
forced-cleanup guidance in the [`run` reference](../reference/cli/run.md#kill).

Do not change `GPTNT_EM_PORT` merely to hide a leftover process. The CLI and all clients must use
the same endpoint.

## A full check fails after configuration passes

`--config-only` intentionally skips infrastructure and machine checks. Run the full report and use
the corresponding subsystem page:

```bash title="Check runtime dependencies"
gptnt doctor runs/<name>.yaml
```

- Game binary, mod, display, or mod-load failures:
  [Game and displays](game-and-displays.md).
- Redis, experiment-manager endpoint, or telemetry warnings:
  [Redis and runtime services](redis-and-runtime-services.md).
- Provider request failure after `--live`: use [provider and model-response troubleshooting](providers-and-model-responses.md)
  with the player and provider configuration that doctor reports. The request can incur provider
  charges.

## An older artefact does not load

!!! warning "Use the matching release"
    V2 tooling does not convert submission schema version 1, prior Parquet layouts, or prior DuckDB
    layouts. It does not upgrade an earlier database in place. Inspect old data with its matching
    release or rerun the benchmark to produce current records.

[Doctor reference](../reference/cli/doctor.md)
[Install and check GPTNT](../start-here/install-and-check.md)
