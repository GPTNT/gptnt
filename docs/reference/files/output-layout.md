---
title: Output layout
tags:
  - Results
  - Runtime
---

# Output layout

`Paths.root` defaults to the current working directory. Environment overrides can relocate any
configured path, including the specification, recorder, database, static, and submission roots.

```text title="Default output layout"
storage/
  ktane/                              # installed game and mods
  prompts/                            # prompt storage
output/
  logs/
    run_<run-output-name>/            # one file per child process
  observations/                       # temporary Dill observation pickles
  experiment_specs/
    <manifest-stem>/
      <attempt-name>.json
  experiment_recorder_outputs/
    <timestamp>/
      experiment-<attempt>-<player-uuid>.parquet
      span_timings/
        <service>-<pid>.jsonl
  experiments.duckdb
  manual_cache/
    artifacts/<sha256>/
    sources/
  <task>_predictions/
    <provider-model>/
      run_meta.json
      prediction_<index>.json
      metrics.json
  how_do_you/
    <provider-model>.json
  submissions/
    <date>_<display>_<fingerprint8>_<target>_<revision>/
```

`EXPERIMENT_RECORDER_OUTPUTS` pins the recorder directory for one run. When it is unset, `run`
creates a timestamped directory under `output/experiment_recorder_outputs/`. The separate
`EXPERIMENT_RECORDER` option tells completion and database commands where existing records live.

## Contract boundaries

- Experiment specifications, player-record Parquet, static metadata and predictions, DuckDB
  tables, and submission bundle members have their documented contracts.
- Observation pickle files, process logs, span-timing JSONL, manual source downloads, and the
  DuckDB WAL are intermediate or implementation-facing artefacts.
- Manual artefacts are content-addressed directories containing their own manifest, PDF, text, and
  page images. Their lifecycle is documented under
  [Manuals](../../run-and-submit/prepare-manuals.md).

!!! warning "Do not infer stability from location"
    A file under `output/` is not automatically a supported format. Use the linked format page to
    determine its compatibility boundary before building another tool around it.
