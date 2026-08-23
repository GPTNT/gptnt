---
title: Add a model
tags:
  - Model integration
  - Configuration
  - Extension API
---

# Add a model

Create a model-backed player profile that passes GPTNT's configuration checks. The profile records
identity and capabilities. Calibration adds the model's image-token cost.

## Before you begin

Complete the [quickstart](../start-here/run-quickstart.md). You also need:

- the model identifier accepted by its Pydantic AI model integration;
- the input and output limits that apply to one request;
- a model page and organisation name for result attribution; and
- a representative manual-page PNG for image-token calibration.

If the model uses a custom endpoint, you will create its player profile here and attach a separate
[provider profile](configure-provider.md) afterwards.

## Scaffold the profile

Choose a configuration name containing only letters, digits, hyphens, and underscore characters.
From the repository root, run:

```bash
gptnt new player my-model
```

The command creates `configs/player/my-model.yaml` and refuses to replace an existing file.

!!! success "The profile is discoverable"
    `gptnt list players` includes `my-model` under **Players**.

The filename is the configuration name used by run manifests. Keep
`capabilities.player_name` the same unless you have a specific reason to give the recorded player a
different name. GPTNT resolves the configuration name to `player_name` before generation and
matchmaking.

## Configure the player

Edit the generated file. The following profile shows the complete local structure. Replace the
model identifier, limits, and attribution with values for your model.

!!! example "Player profile"
    ```yaml title="configs/player/my-model.yaml" annotations
    # @package player

    defaults:
      - _self_

    capabilities:
      player_name: my-model # (1)!
      thinking_method: thinking-out-loud
      structured_output_mode: null
      include_schema_in_instructions: true
      interaction_location_method: set-of-marks
      usage_limits:
        input_tokens_limit: 200000
        output_tokens_limit: 64000

    identity:
      display_name: My Model
      organisation: My Organisation
      is_os_model: false
      url: https://example.com/models/my-model

    action_predictor:
      agent:
        model: anthropic:my-model # (2)!
        model_settings:
          thinking: false
    ```

    1. GPTNT copies `player_name` into specifications, matchmaking heartbeats, records, and
       submissions. It is distinct from the configuration filename and display name.
    2. The short form lets Pydantic AI select the default provider for the model prefix. A provider
       override requires the explicit model form described on the provider procedure.

The profile inherits the player service, observation processors, recorder, and default fields from
`configs/player.yaml`. The [player configuration reference](../reference/configuration/players.md)
separates those GPTNT-owned fields from Pydantic AI settings.

!!! warning "Keep the capability combination valid"
    `thinking-out-loud` requires `structured_output_mode: null`. The `prompted` output mode always
    includes the schema, so `include_schema_in_instructions` cannot be `false`. Normalised
    coordinates require `coordinate_scale`. Absolute coordinates reject it.

Capabilities change prompt construction, image processing, action parsing, and the participant
recorded with a result. Read [roles, protocols, and capabilities](../understand/roles-protocols-and-capabilities.md)
before changing them for a comparison run.

## Configure endpoint access

The short model form uses the default provider and its standard credential environment variable.
For a custom endpoint, self-hosted service, or non-default provider, continue with
[Configure a provider](configure-provider.md) and return here afterwards.

## Measure the image-token cost

GPTNT uses `tokens_per_image` when deciding how much conversation history fits in a request. The
scaffold leaves the value unset, and the resolved capability default is `0`. Measure it against the
configured endpoint:

```bash
gptnt measure-tokens-per-image my-model path/to/manual-page.png
```

Pass `--provider <name>` when the player needs a provider override. The command resizes the PNG to
the portrait dimensions used for manual pages, makes one request without the image and one with it,
then writes their positive input-token difference to `configs/player/my-model.yaml`.

!!! warning "Calibration calls the provider twice"
    The command sends two model requests and can incur provider charges. Use the same player and
    provider combination that the run manifest will use.

!!! success "Calibration was stored"
    The output table reports the baseline, the request with one image, and `tokens per image`. The
    final line names the updated player file.

## Validate the player

Run the configuration-only checks:

```bash
gptnt doctor --config-only
```

Without a manifest, doctor checks every discovered player. The new profile must pass composition,
agent construction, and the image-token row. A missing credential fails construction and names the
environment variable reported by Pydantic AI.

To make one endpoint request per discovered player, add `--live`:

```bash
gptnt doctor --config-only --live
```

!!! warning "The live check can incur charges"
    `--live` sends one provider request for each checked player. A later manifest-specific check
    limits this to the player and provider pairs in that manifest.

Use [provider and model-response troubleshooting](../troubleshooting/providers-and-model-responses.md)
when composition succeeds but construction, calibration, or a live request fails.

## Continue

Create any required [provider profile](configure-provider.md), then [prepare the selected
manuals](../manuals.md) and [create a run manifest](create-run-manifest.md). When configuration is
not enough for an integration, use the [supported player interfaces](../reference/python/player-interfaces.md).
