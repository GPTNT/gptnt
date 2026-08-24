---
title: Static evaluation outputs
tags:
  - Results
  - Submission
---

# Static evaluation outputs

Dataset-backed static tasks write a model-specific directory with run metadata, one JSON file per
prediction, and task-dependent metrics. These formats have no independent format version.

```text title="Dataset task layout"
output/
  <task>_predictions/
    <provider-model>/
      run_meta.json
      prediction_0.json
      prediction_1.json
      ...
      metrics.json
```

## Run metadata

::: gptnt.statics.run_metadata.StaticsIdentity
    options:
      show_root_heading: true
      members:
        - is_pinned
        - revision_label
        - target

::: gptnt.statics.run_metadata.StaticsRunMetadata
    options:
      show_root_heading: true

`requested_revision` is the branch, tag, or commit supplied to the dataset loader.
`resolved_revision` is the concrete dataset commit resolved before prediction. A resumed output
set keeps its original run date and resolved commit. Prediction files without metadata cannot be
resumed because current provenance cannot be assigned to earlier calls.

## Prediction files

Each `prediction_<index>.json` adds the dataset row `index` to `ModelOutput`:

::: gptnt.statics.eval_model.ModelOutput
    options:
      show_root_heading: true

`output` is the parsed task output before score normalisation. `scored_output` is the canonical
task answer used by current scorers. `error` records response-validation classifications;
`exception` records a structured traceback when prediction did not complete. `usage` omits zero
token counts.

## Metrics

`metrics.json` is a task-dependent `dict[str, dict[str, value]]` written after local scoring. It is
not a cross-task schema. Static submission copies this file verbatim and uses `run_meta.json` for
the player, capabilities, task, dataset, run date, and provenance.

!!! warning "Limit changes the output boundary"
    `--limit-instances` writes and scores only the loaded prefix. Do not treat a limited diagnosis
    run as complete task coverage.

## `how-do-you`

`output/how_do_you/<provider-model>.json` maps each supported module to a list of attempts. Each
attempt contains `prompt` and `response`. An optional prefix changes the filename. This command
writes no `run_meta.json` or `metrics.json` and is not a dataset-backed submission target.
