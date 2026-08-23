---
title: Experiment specifications
tags:
  - Configuration
  - Results
---

# Experiment specifications

`gptnt generate` writes one JSON file per experiment attempt. The filename is
`<attempt_name>.json`; readers load every `*.json` recursively from the selected directory.

The format has no independent version field. Its compatibility is the current `ExperimentSpec`
schema plus the frozen suite identity embedded in each file.

## Stored relationships

Each specification combines:

- the exact materialised `mission_spec` and its mission-set name;
- the one-based generator-assigned `attempt`;
- suite name, frozen revision, and suite digest;
- the ordered manual profile;
- the Defuser protocol and `player_name`; and
- an Expert protocol and `player_name`, or two null Expert values.

The Defuser and Expert names are player `player_name` values resolved during generation, not
necessarily the configuration filenames used in a run manifest. Runtime service UUIDs, resolved
capabilities, session time, records, and outcomes are not part of a specification.

`fingerprint` identifies the mission, frozen suite, manual profile, and protocols. It excludes the
attempt number and player names. `attempt_name` includes the suite revision, mission set,
communication style, modules, seeds, pairing, and attempt.

## Generated schema

::: gptnt.experiments.spec.ExperimentSpec
    options:
      show_root_heading: true
      members:
        - fingerprint
        - communication_style
        - experiment_name
        - attempt_name

!!! note "Expert fields move together"
    `expert_protocol` and `expert_name` must either both be present or both be null. A solo Defuser
    requires both Expert fields to be null.

Generate files into the path that the run command reads:

```bash
gptnt generate runs/<name>.yaml
gptnt run runs/<name>.yaml
```

[Run interactive experiments](../../running/run-your-model.md){ .md-button }
[Generation API](../python/experiment-generation.md){ .md-button }
