---
title: Providers and model responses
tags:
  - Troubleshooting
---

# Providers and model responses

Start with the failing row from `gptnt doctor`. It identifies the player configuration and any
provider override that GPTNT composed.

## The player or provider name is not listed

Run:

```bash title="List player configurations"
gptnt list players
```

Player profiles must be YAML files directly under `configs/player/`. Provider overrides must be
under `configs/player/provider/`. Use the filename without `.yaml` in a run manifest or command
option. Files whose names begin with an underscore are not selectable configurations.

## A provider override cannot be applied to the model

A model configured as a short string, such as `openai:gpt-5`, is already a complete Pydantic AI
model setting. GPTNT cannot merge a provider override into that string.

Change `action_predictor.agent.model` to an explicit model configuration containing `_target_`,
`model_name`, and `provider`. Then repeat the doctor command with `--provider <name>` or validate the
run manifest that pairs them.

Use [Configure a provider](../running/configure-provider.md) for the supported composition pattern.

## Doctor reports a missing credential

The selected Pydantic AI provider declares its credential environment variable. Set it in the
environment that runs GPTNT, then start a new shell or export it before running doctor again.

Do not put API keys in player YAML, provider YAML, run manifests, or committed `.env` files. The
[Pydantic AI model documentation](https://ai.pydantic.dev/models/) lists credential requirements
for each integration.

For a self-hosted endpoint that does not require authentication, configure the provider according
to its official API instead of inventing a placeholder secret.

## The configuration check passes but the endpoint does not respond

Use a live doctor check for the affected run or player:

```bash title="Check provider access"
gptnt doctor runs/<name>.yaml --live
gptnt doctor --player <player> --provider <provider> --live
```

!!! warning "A live check can spend money"
    `--live` sends one request to every checked model endpoint. Restrict the command to the player
    and provider you are diagnosing when the provider charges per request.

If the check fails, confirm network access and the provider's base URL, model name, and
authentication. GPTNT passes provider-specific fields to Pydantic AI. Use the
[Pydantic AI provider documentation](https://ai.pydantic.dev/models/) for accepted fields and the
service operator's API documentation for endpoint behaviour.

## Image-token measurement is zero or negative

`gptnt measure-tokens-per-image` makes two requests with the same prompt and compares their input
usage, adding a calibration image to one request. A nonpositive difference means the response usage
did not expose a usable image-token cost.

Check that the selected model accepts images, the provider returns input-token usage, and the
calibration image reaches the model. Then repeat the command with the same provider override used
by the run.

!!! warning "Measurement makes paid requests"
    Each measurement makes two provider calls. Check prices and quotas before repeating it.

## The endpoint responds but GPTNT rejects the output

Compare the configured capabilities with the endpoint's output features:

- `thinking-out-loud` requires `structured_output_mode: null`.
- `prompted` output always includes the schema in the instructions.
- Native or tool output requires a provider and model combination that supports that mode.
- Normalised coordinates require `coordinate_scale`. Absolute coordinates reject it.
- Image-bearing suites require a model that can consume the processed images sent by GPTNT.

The runtime does not infer or enforce suite modality from provider metadata. Correct the player
capabilities, or select a model and output mode that match the suite. Use the
[Pydantic AI output documentation](https://ai.pydantic.dev/output/) for provider-facing output
support.

## Requests hit usage limits

`usage_limits` is an operational ceiling for one player call path. Raise it only after checking the
expected context size and provider cost. Pydantic AI defines the available counters and when it
checks them in its [usage-limit reference](https://ai.pydantic.dev/api/usage/#pydantic_ai.usage.UsageLimits).

After correcting the configuration, rerun `gptnt doctor` without `--live` first. Use another live
request only when endpoint reachability or response support still needs confirmation.
