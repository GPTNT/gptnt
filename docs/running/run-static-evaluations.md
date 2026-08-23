---
title: Run static evaluations
tags:
  - CLI
  - Results
  - Model integration
---

# Run static evaluations

Run a configured player against a static dataset and write predictions, metrics, dataset identity,
capabilities, and benchmark provenance without starting KTANE.

## Before you start

Complete the player and provider checks described in
[Add a model](add-new-player.md). Choose a task from `gptnt statics --help`.

For a submission, run the three required interactive suites and the explicit
`expert-vqa-no-manual` static target described in
[Submit your results](../submit-your-results.md#prepare-the-required-results).

## Preview a task

Every dataset-backed command requires `--player`. `--provider` selects an optional provider
override.

```bash
gptnt statics expert-vqa-no-manual --player <player-name>
```

Without `--throw`, the command constructs the evaluation but does not execute predictions. Add a
small limit while checking a player:

```bash
gptnt statics expert-vqa-no-manual \
  --player <player-name> \
  --limit-instances 3 \
  --throw
```

!!! note "The option is `--player`"
    Static commands select `configs/player/<name>.yaml` with `--player`. They do not accept the
    older `--model` spelling.

## Pin and run the dataset

Supply a Hugging Face branch, tag, or commit with `--dataset-revision`. GPTNT resolves the request
to a concrete dataset commit before the first prediction and records both values.

```bash
gptnt statics expert-vqa-no-manual \
  --player <player-name> \
  --dataset-revision <commit-or-tag> \
  --throw
```

The output directory is `output/<task>_predictions/<provider-model>/`. Before the first prediction,
GPTNT writes `run_meta.json`. Each completed instance writes `prediction_<index>.json`; scoring
writes `metrics.json`.

If a prediction file already exists, a resumed run skips that index. The stored run date and
resolved dataset commit remain bound to the output set. GPTNT rejects a resume when existing
predictions have no `run_meta.json`, or when the stored metadata conflicts with the current player,
capabilities, task, dataset, or provenance.

!!! warning "Keep dataset and benchmark identity with the output"
    A requested tag or branch can move. Comparability uses the resolved dataset commit recorded in
    `run_meta.json`. Running with `--allow-modified-benchmark` marks the static output as modified
    protected content and prevents submission.

## Check the output

Confirm that the directory contains `run_meta.json`, the expected prediction indices, and
`metrics.json`. The submission builder copies the metrics and reads the metadata; it does not infer
identity from the directory name.

See [Statics command reference](../reference/cli/statics.md) for every task and option, and
[Static evaluation outputs](../reference/files/static-evaluation-outputs.md) for the stored fields.

<!-- vale ai-tells.DoubleHyphen = NO -->
[Inspect results](inspect-results.md){ .md-button .md-button--primary }
[Understand comparability](../understand/suites-revisions-and-comparability.md){ .md-button }
<!-- vale ai-tells.DoubleHyphen = YES -->
