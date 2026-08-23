---
title: Suite configuration
tags:
  - Configuration
  - Results
---

# Suite configuration

Suite YAML composes a frozen benchmark definition: missions, protocols, pairing policy, manual
profile, modalities, and revision. Live YAML is an authoring input. Specification generation reads
the corresponding entry from `configs/suites/suites.lock`.

## Authoring shape

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

::: gptnt.experiments.suite.core.Suite
    options:
      show_root_heading: true
      members:
        - mission_set
        - config_digest
        - suite_digest

::: gptnt.experiments.suite.core.SuiteMatchup
    options:
      show_root_heading: true

::: gptnt.experiments.suite.core.SuiteIdentity
    options:
      show_root_heading: true
      members:
        - target

::: gptnt.players.specification.PlayerProtocol
    options:
      show_root_heading: true

For `config_digest`, `name`, `revision`, and mission bodies are excluded. `suite_digest` adds the
materialised mission snapshot. The exact frozen lock structure is documented with
[submission bundles](../files/submission-bundles.md) and comparability is explained in
[Suites, revisions, and comparability](../../understand/suites-revisions-and-comparability.md).
