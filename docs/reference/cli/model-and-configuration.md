---
title: Model and configuration commands
tags:
  - CLI
  - Model integration
---

# Model and configuration commands

These commands create player and provider profiles, list selectable configurations, and measure a
player's image-token cost.

## `gptnt new player`

```text title="Command syntax"
gptnt new player NAME
```

| Input | Contract |
| ----- | -------- |
| `NAME` | Required. Letters, digits, `-`, and `_` only. |
| Output | `configs/player/<NAME>.yaml` from the current player scaffold. |

The command creates parent directories when needed and refuses to overwrite an existing profile.
Its completion message recommends `gptnt doctor`.

## `gptnt new provider`

```text title="Command syntax"
gptnt new provider NAME
```

`NAME` has the same character constraint as a player name. The command writes
`configs/player/provider/<NAME>.yaml` and refuses to overwrite an existing profile. The scaffold
uses an OpenAI-compatible provider as an editable example.

## `gptnt list players`

```text title="Command syntax"
gptnt list players
```

The command takes no arguments. It prints sorted player profile names from `configs/player/*.yaml`.
When provider profiles exist, it prints a separate sorted **Providers** group from
`configs/player/provider/*.yaml`.

## `gptnt list suites`

```text title="Command syntax"
gptnt list suites
```

The command takes no arguments. It prints sorted suite names from `configs/suites/*.yaml` and omits
underscore-prefixed templates.

## `gptnt measure-tokens-per-image`

```text title="Command syntax"
gptnt measure-tokens-per-image PLAYER CALIBRATION-IMAGE [--provider PROVIDER]
```

| Input | Contract |
| ----- | -------- |
| `PLAYER` | Required player profile name under `configs/player/`. |
| `CALIBRATION-IMAGE` | Required existing manual-page PNG. |
| `--provider PROVIDER` | Optional provider profile override under `configs/player/provider/`. |

The command composes the player and provider, loads the configured capabilities and agent, and
resizes the PNG to the portrait orientation derived from `image_dimensions`. It sends the same
prompt once without an image and once with the image. The difference between the reported input
token counts becomes `capabilities.tokens_per_image` in the player YAML.

!!! warning "This command sends two model requests"
    Calibration can incur provider charges. The command preserves the agent's configured model
    settings and raises the output allowance to at least 256 tokens for calibration.

A zero or negative difference fails instead of updating the file. This can indicate that the
provider does not include image tokens in its input-token report.
