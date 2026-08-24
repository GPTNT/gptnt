---
title: Submission bundles
tags:
  - Submission
  - Results
---

# Submission bundles

A bundle is one flat directory for one Defuser capability fingerprint and one measured target.
`submission.yaml` uses submission schema version **2**.

```text title="Interactive bundle layout"
output/submissions/
  YYYYMMDD_<display-slug>_<fingerprint8>_<target>_<revision>/
    submission.yaml
    suite.lock
    experiments.parquet
```

Static bundles replace `suite.lock` and `experiments.parquet` with `metrics.json`.

`suite.lock` is a reduced snapshot of the canonical `configs/suites/suites.lock`: it contains one
recorded suite revision and exactly the mission bodies that entry references.

## Manifest

The `measured` block discriminates the two bundle shapes. A suite identity selects an interactive
bundle. A static task and dataset identity selects a static bundle.

::: gptnt.cli.submission._schema.Submitter
    options:
      show_root_heading: true

::: gptnt.cli.submission._schema.SubmissionPlayer
    options:
      show_root_heading: true

::: gptnt.cli.submission._schema.InteractiveSubmission
    options:
      show_root_heading: true

::: gptnt.cli.submission._schema.StaticsSubmission
    options:
      show_root_heading: true

The Defuser is first in `players`. Each entry combines role, recorded capabilities, a recomputed
capability fingerprint, and leaderboard attribution loaded from the player configuration.
`submission_id` and the directory name are derived from run date, player, target, and fingerprint.

## Interactive payload

`experiments.parquet` contains one `SubmissionExperiment` row per selected execution:

::: gptnt.cli.submission._schema.SubmissionExperiment
    options:
      show_root_heading: true

The row extends `ExperimentSummary` with the terminal bomb state and usage summed separately for
the Defuser and Expert. It does not contain complete step trajectories.

Validation checks the reduced lock identity and digest, exact mission snapshot, one valid run per
expected player pairing and mission, player fingerprints, provenance, bundle naming, and payload
shape without reading live suite or mission configuration.

## Static payload

`metrics.json` is copied verbatim from the task output. The manifest supplies the task, Hugging
Face repository and split, requested and resolved revisions, player, capabilities, run date, and
benchmark provenance.
