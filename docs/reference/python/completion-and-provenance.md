---
title: Completion and provenance API
tags:
  - Extension API
  - Results
---

# Completion and provenance API

These package APIs define experiment completion and benchmark provenance. A completion source can
change where status is read, but not the rule for a valid terminal outcome.

## Completion ledgers

::: gptnt.experiments.ledger.CompletionLedger
    options:
      show_root_heading: true

::: gptnt.experiments.ledger.LocalLedger
    options:
      show_root_heading: true
      members:
        - status_for
        - completed

::: gptnt.experiments.ledger.Source
    options:
      show_root_heading: true

::: gptnt.experiments.ledger.resolve_ledger
    options:
      show_root_heading: true

::: gptnt.experiments.ledger.filter_experiments
    options:
      show_root_heading: true

`ExperimentStatus` is `done`, `failed`, `not_attempted`, or `running`. The local ledger does not
report `running` by itself. The CLI status command adds that state from the experiment manager.

## Provenance and integrity

::: gptnt.provenance.Provenance
    options:
      show_root_heading: true
      members:
        - capture

::: gptnt.provenance.BenchmarkIntegrityError
    options:
      show_root_heading: true

::: gptnt.provenance.check_benchmark_integrity
    options:
      show_root_heading: true

::: gptnt.provenance.gptnt_version
    options:
      show_root_heading: true

::: gptnt.provenance.git_sha
    options:
      show_root_heading: true

::: gptnt.provenance.is_valid_version
    options:
      show_root_heading: true

Stored provenance is complete at record creation. A later reader never fills missing values from
its checkout. Benchmark integrity requires one exact annotated `vMAJOR.MINOR.PATCH` tag on the
release commit; an absent or ambiguous tag raises `BenchmarkIntegrityError`.
