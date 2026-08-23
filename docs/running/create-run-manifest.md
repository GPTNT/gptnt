---
title: Create a run manifest
tags:
  - Configuration
  - CLI
---

# Create a run manifest

Create a schema-v2 YAML manifest that selects suites, a player roster, runtime capacity, and resume
behaviour. Finish with a passing doctor report and generated experiment specifications.

## Before you begin

You need:

- a checked installation and completed quickstart;
- each required [player](add-new-player.md) and [provider](configure-provider.md);
- the manual profile selected by each suite, prepared as described in [Prepare manuals](../manuals.md);
  and
- enough player processes and game rooms for the selected suite protocols.

List the available names before editing:

```bash title="List available configurations"
gptnt list suites
gptnt list players
```

`list players` prints player profiles and provider profiles in separate groups.

## Copy the template

Run this command from the repository root:

```bash title="Create the manifest"
cp runs/_template.yaml runs/my-run.yaml
```

Edit the copy. This complete manifest uses one custom player through a provider override and one
included player:

!!! example "Schema-v2 manifest"
    ```yaml title="runs/my-run.yaml" annotations
    spec_version: 2

    suites:
      - single-pairwise-sync # (1)!

    rooms: 1

    players:
      - player: my-model # (2)!
        provider: my-provider # (3)!
      - player: test-expert

    source: local
    observability: limited
    ```

    1. A suite name is the filename under `configs/suites/` without `.yaml`.
    2. `player` selects a configuration filename, not `capabilities.player_name` or the display
       name. Doctor resolves and cross-checks those names.
    3. `provider` attaches the matching profile under `configs/player/provider/`. Omit it when the
       player uses the model integration's default provider.

The [run-manifest reference](../reference/configuration/run-manifest.md) gives every field, default,
and constraint.

## Set runtime capacity

`rooms` is the number of game-service processes. Each player entry's `count` is the number of
player-service processes created from that profile; it defaults to `1`.

Capacity depends on the selected suite protocols. A two-role experiment needs concurrent Defuser
and Expert services. A solo protocol needs one player. Self-play still needs separate service
processes for concurrent roles. Use `count` to supply the concurrency you intend; doctor reports
the declared roster and generated appearances.

On Linux, `displays` assigns rooms to X display numbers in round-robin order. Omit it to preserve
the ambient `DISPLAY` value.

## Add anchors or more attempts when required

`with_best_expert` and `with_best_defuser` pairings read their fixed player configuration names
from `anchors`. An anchor used by the selected suites must also have a roster entry so the run
starts its player service.

```yaml
anchors:
  best_expert: test-expert
```

`attempts_per_mission` controls generation depth for each mission and pairing. It defaults to `1`
and does not form part of suite identity.

!!! warning "Configuration choices affect result identity"
    Suite revisions and digests identify what is measured. Player capabilities and selected model
    settings identify the participant. Keep the generated specifications with the configuration
    used to produce them.

## Validate the manifest

Run the full check:

```bash title="Validate the run manifest"
gptnt doctor runs/my-run.yaml
```

Doctor validates the YAML and composes each player and provider pair. It checks the run roster
against the selected suites and reports resume state before checking local infrastructure.

!!! success "The run plan passes"
    Player rows pass composition and construction. The **Run plan** section reports roster
    coverage and the number of generated specifications without a failing row.

Use [installation and doctor troubleshooting](../troubleshooting/installation-and-doctor.md) for a
manifest or roster failure. Use [provider troubleshooting](../troubleshooting/providers-and-model-responses.md)
for a failed model row.

## Generate the specifications

```bash title="Generate specifications"
gptnt generate runs/my-run.yaml
```

The command writes one JSON file per attempt under
`output/experiment_specs/my-run/`.

!!! success "Specifications were written"
    The final line reports the specification count and destination directory.

`gptnt run` does not regenerate specifications. Regenerate them after changing the manifest or a
selected configuration that affects the experiments. Continue with [Run your model](run-your-model.md#interactive-experiments).
