---
title: Experiment generation API
tags:
  - Extension API
  - Configuration
---

# Experiment generation API

These objects form the supported Python boundary for constructing suite identities, mission and
player pairings, experiment specifications, and frozen suite snapshots. CLI workflows should use
`generate-missions`, `suite freeze`, and `generate` instead.

## Suites and pairings

::: gptnt.experiments.suite.definition.Suite
    options:
      show_root_heading: true
      members:
        - digest_for
        - mission_set
        - config_digest
        - suite_digest

::: gptnt.experiments.suite.definition.SuiteMatchup
    options:
      show_root_heading: true

::: gptnt.experiments.suite.definition.SuiteIdentity
    options:
      show_root_heading: true
      members:
        - target

::: gptnt.experiments.generation.pairing.Pairing
    options:
      show_root_heading: true

::: gptnt.experiments.generation.pairing.PairingGenerator
    options:
      show_root_heading: true
      members:
        - generate

## Missions and specifications

::: gptnt.experiments.generation.missions.MissionGeneratorConfig
    options:
      show_root_heading: true

::: gptnt.experiments.generation.missions.MissionGenerator
    options:
      show_root_heading: true
      members:
        - generate

::: gptnt.experiments.generation.experiments.ExperimentGenerator
    options:
      show_root_heading: true
      members:
        - generate

::: gptnt.experiments.spec.ExperimentSpec
    options:
      show_root_heading: true

## Frozen snapshots

::: gptnt.experiments.suite.lock.SuiteLock
    options:
      show_root_heading: true
      members:
        - from_lock_path
        - select_entry
        - load_suite
        - snapshot

The generator assigns attempts starting at one. `ExperimentSpec` requires expert protocol and
expert name to be either both present or both absent, and forbids an Expert for a solo Defuser.
