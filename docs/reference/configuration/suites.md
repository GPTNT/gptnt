---
title: Suite configuration
tags:
  - Configuration
  - Results
---

# Suite configuration

Suite YAML defines missions, protocols, pairing policy, manual profile, modalities, and revision.
`suite freeze` records a frozen revision in `configs/suites/suites.lock`. Specification generation
reads that frozen revision rather than the current YAML.

## Configuration shape

Files under `configs/suites/` use Hydra's `_target_` keys to construct `Suite`, `SuiteMatchup`,
`PlayerProtocol`, and `ManualProfile`. Start from `configs/suites/_template.yaml`.

`PairingType` accepts:

- `with_self` for the same configured player in both roles;
- `pairwise` for every ordered Defuser and Expert pairing;
- `with_best_defuser` or `with_best_expert` for an anchor from the run manifest; and
- `no_expert` for a solo Defuser protocol.

The `defuser_protocol` role must be `defuser`. An `expert_protocol`, when present, must use
`expert`. A solo Defuser cannot have an Expert.

!!! warning "Increase the revision when measured content changes"
    `suite freeze` rejects a changed suite digest at an existing name and revision. Increase the
    revision, then freeze the new configuration and mission snapshot.

`modality` is sorted and deduplicated before digest calculation. Current v2 scheduling does not
enforce the value against player capabilities.

## Generated models

::: gptnt.experiments.suite.definition.Suite
    options:
      show_root_heading: true
      members:
        - mission_set
        - digest

::: gptnt.experiments.suite.definition.SuiteMatchup
    options:
      show_root_heading: true

::: gptnt.experiments.suite.definition.SuiteIdentity
    options:
      show_root_heading: true
      members:
        - target

::: gptnt.players.specification.PlayerProtocol
    options:
      show_root_heading: true

`digest` covers the materialised mission bodies, manual profile and rule seed, role protocols,
matchup, and modalities. It excludes the suite name, revision, configuration path, and freeze
provenance. The lock version defines the digest recipe. The exact frozen lock structure is
documented with [submission bundles](../files/submission-bundles.md) and comparability is explained
in [Suites, revisions, and comparability](../../understand/suites-revisions-and-comparability.md).
