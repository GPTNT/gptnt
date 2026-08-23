---
title: generate
tags:
  - CLI
  - Configuration
---

# `generate`

`gptnt generate` composes a run manifest into persisted experiment specifications. It validates
configuration and benchmark integrity without checking runtime infrastructure.

## Usage

```text title="Command syntax"
gptnt generate MANIFEST [--output-dir PATH] [--allow-modified-benchmark]
```

| Input or option | Required | Effect |
| --------------- | -------- | ------ |
| `MANIFEST` | Yes | Existing `run.yaml` manifest to compose. |
| `--output-dir PATH` | No | Writes specifications to this directory. Also reads `EXPERIMENT_SPECS_DIR`. |
| `--allow-modified-benchmark` | No | Uses the contributor integrity override when available and records modified protected content in later provenance. |

The command performs these operations in order:

1. Load and validate `RunManifest`.
2. Check benchmark integrity and the selected player roster without runtime infrastructure.
3. Compose the suites, missions, pairings, players, and attempts into `ExperimentSpec` objects.
4. Write one JSON file per specification.

## Default output

Without an override, the output directory is:

```text title="Default output directory"
output/experiment_specs/<manifest-stem>/
```

Each file uses the `<attempt_name>.json` pattern. `gptnt run runs/<name>.yaml` later reads every
`*.json` file recursively from `output/experiment_specs/<name>/`.

```bash title="Generate specifications"
gptnt generate runs/quickstart.yaml --output-dir output/experiment_specs/quickstart # (1)!
```

1. The explicit path matches the default for `runs/quickstart.yaml`. Use the option only when you
   need another location.

!!! success "Specifications were written"
    The command prints `Wrote <count> spec(s) to <path>` after all JSON files are written.

!!! failure "Nothing is written after a failed gate"
    A failed integrity, player, roster, or composition check stops before the output operation. An
    empty generated plan also stops with `No experiment specs were generated from this manifest.`

!!! warning "Generated specifications retain benchmark identity"
    A specification records the selected suite name, revision, and digest. Regenerate after
    changing a manifest, suite selection, mission input, protocol, player selection, or attempt
    count. Do not mix files generated from incompatible inputs in one output directory.

[Run the quickstart](../../start-here/run-quickstart.md)
[Run generated specifications](run.md)
