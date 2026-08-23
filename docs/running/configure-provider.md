---
title: Configure a provider
tags:
  - Model integration
  - Configuration
---

# Configure a provider

Connect a player to its inference endpoint without storing credentials in a tracked player,
provider, or run-manifest file.

## Choose the access path

A Pydantic AI model string such as `anthropic:<model-name>` selects that model integration's
default provider. Create a GPTNT provider profile when you need to attach a different endpoint,
client, or provider to the same player.

=== "Hosted provider"

    Keep the short model string when the default provider is sufficient. Set the credential in the
    environment named by that provider, then continue to [verify access](#verify-access).

    If the hosted service needs a non-default provider or SDK client, scaffold a provider profile:

    ```bash
    gptnt new provider my-provider
    ```

    Replace the scaffold target and fields with the values required by the
    [Pydantic AI provider documentation](https://pydantic.dev/docs/ai/models/overview/).

=== "Self-hosted provider"

    Scaffold an endpoint profile:

    ```bash
    gptnt new provider my-vllm
    ```

    OpenAI-compatible services use an explicit model object in the player profile:

    ```yaml title="configs/player/my-model.yaml"
    action_predictor:
      agent:
        model:
          _target_: pydantic_ai.models.openai.OpenAIChatModel
          model_name: my-served-model
    ```

    Configure the endpoint separately:

    ```yaml title="configs/player/provider/my-vllm.yaml" annotations
    # @package player.action_predictor.agent.model # (1)!

    provider:
      _target_: pydantic_ai.providers.openai.OpenAIProvider
      base_url: http://localhost:8000/v1
      api_key: ${oc.env:VLLM_API_KEY}
    ```

    1. GPTNT composes this mapping into the selected player's model node. The endpoint is not a
       global provider setting.

    Use the provider or SDK client's official API reference for its accepted endpoint, client,
    authentication, and header fields.

!!! warning "Keep credentials outside tracked configuration"
    Store API keys and access tokens in environment variables. Hydra's `${oc.env:NAME}` form reads
    them when the configuration is composed. Do not commit a credential or place it in a run
    manifest.

## Attach the provider

Select the provider beside the player in a run manifest:

```yaml
players:
  - player: my-model
    provider: my-vllm
```

`player` selects `configs/player/my-model.yaml`. `provider` selects
`configs/player/provider/my-vllm.yaml`. Static and calibration commands use the same optional
`--provider my-vllm` selection.

!!! failure "A provider override replaces a short model string"
    A provider profile merges beneath `action_predictor.agent.model`. If that node is a short model
    string, the merge removes the model class. Use the explicit `_target_` model form before
    attaching an override. Doctor reports this combination during configuration checks.

The [provider configuration reference](../reference/configuration/providers.md) lists GPTNT's
composition boundary and checked-in examples. Pydantic AI owns provider-specific fields, model
lists, credential names, and client behaviour.

## Verify access

First validate composition and construction without infrastructure checks:

```bash
gptnt doctor runs/my-run.yaml --config-only
```

Then make one request for each player and provider pair in the manifest:

```bash
gptnt doctor runs/my-run.yaml --config-only --live
```

!!! warning "The live check can incur charges"
    `--live` sends one model request for every player entry in the manifest. Use it only after the
    static configuration checks pass.

!!! success "The endpoint answered"
    The model row passes **Exists**, **Inst.**, and **Live**. The row's note shows how long the
    response took.

If the row fails, follow [provider and model-response troubleshooting](../troubleshooting/providers-and-model-responses.md).
After access works, [create the run manifest](create-run-manifest.md) that will use this combination.
