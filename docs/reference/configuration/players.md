---
title: Player configuration
tags:
  - Configuration
  - Model integration
---

# Player configuration

A player profile under `configs/player/<name>.yaml` overrides the base Hydra assembly in
`configs/player.yaml`. The resolved configuration constructs a player service, model agent,
capabilities, identity, recorder, and observation processors.

## Configuration ownership

| Subtree | Owner |
| ------- | ----- |
| `capabilities` | GPTNT's participant input, output, processing, and identity settings |
| `identity` | GPTNT's submission attribution |
| `action_predictor` | GPTNT's predictor around a Pydantic AI agent |
| `action_predictor.agent.model` | Pydantic AI model selection and provider attachment |
| `action_predictor.agent.model_settings` | Pydantic AI generic or provider-specific request settings |
| `observation_handler` | GPTNT's resizing, set-of-marks, and coordinate conversion |
| `experiment_recorder` | GPTNT's local or W&B recorder target |

Use the [Pydantic AI model overview](https://pydantic.dev/docs/ai/models/overview/),
[`ModelSettings` API](https://pydantic.dev/docs/ai/api/pydantic-ai/settings/), and
[`UsageLimits` API](https://pydantic.dev/docs/ai/api/pydantic-ai/usage/) for fields owned by that
library. GPTNT does not duplicate provider model lists or settings fields.

## Capability relationships

`usage_limits` applies Pydantic AI request limits. GPTNT also uses its input-token limit when
truncating conversation history. `tokens_per_image` adds the calibrated token value for every
image in that calculation.

`model_settings` on `PlayerCapabilities` is derived by the base Hydra configuration from
`action_predictor.agent.model_settings`. Do not maintain a second authored copy. The derived value
retains model-input and generation settings used by the capability fingerprint while omitting the
operational settings excluded by `fingerprint_model_settings`.

!!! warning "Capabilities are benchmark identity"
    Image dimensions, token measurement, thinking mode, structured output, observation retention,
    location representation, feedback generation, and selected model settings can change model
    input or output. Record and compare them as part of the configured participant.

## Player identity

::: gptnt.players.specification.PlayerIdentity
    options:
      members: false

## Player capabilities

::: gptnt.players.specification.PlayerCapabilities
    options:
      members:
        - normalised_coordinate_scale
        - interact_location_type
        - fingerprint

## Image dimensions

::: gptnt.common.image_ops.ImageDimensions
    options:
      members:
        - long_side
        - short_side

## Observation processing

The base profile supplies `ObservationHandler`, `ImageResizer`, and `SetOfMarksHandler`. Override
their Hydra subtrees only when the player needs different image dimensions, coordinate handling, or
mark rendering. Their callable contracts are grouped in the [processor reference](../python/processors.md).

[Add a model](../../run-and-submit/add-model.md)
[Understand capabilities](../../understand/roles-protocols-and-capabilities.md)
