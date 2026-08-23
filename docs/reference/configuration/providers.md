---
title: Provider configuration
tags:
  - Configuration
  - Model integration
---

# Provider configuration

A provider profile under `configs/player/provider/<name>.yaml` is a Hydra override for
`player.action_predictor.agent.model.provider`. A run-manifest roster entry or a command's
`--provider` option selects it beside one player profile.

## Local composition contract

| Local element | Contract |
| ------------- | -------- |
| `# @package player.action_predictor.agent.model` | Places the profile beneath the selected model node. |
| `provider._target_` | Hydra target for the Pydantic AI provider or provider factory. |
| `PlayerSpec.provider` | Selects the provider profile for one interactive roster entry. |
| `--provider` | Selects the same override for calibration and static commands that expose it. |

The model node must use an explicit `_target_` form when a provider profile is attached. A short
model string is replaced by the nested provider mapping and therefore cannot retain its model
class. Doctor detects this conflict.

## Checked-in profiles

| Profile | Local target pattern |
| ------- | -------------------- |
| `anthropic` | `AnthropicProvider` |
| `anthropic_foundry` | `AnthropicProvider` with an `AsyncAnthropicFoundry` client |
| `azure` | `AzureProvider` |
| `gateway_vertex` | Pydantic AI's gateway provider factory for Google Vertex |
| `google` | `GoogleProvider` with GPTNT's cached retrying HTTP client |
| `openai` | `OpenAIProvider` |
| `vllm_box1` through `vllm_box4` | `OpenAIProvider` with an `AsyncOpenAI` client, endpoint, and access headers |

These profiles are local examples, not a complete provider field catalogue. Provider constructors,
model lists, SDK-client fields, credential environment variables, and endpoint semantics belong to
the [Pydantic AI provider documentation](https://pydantic.dev/docs/ai/models/overview/) and the
linked provider SDKs.

!!! warning "Do not commit credentials"
    Use environment interpolation such as `${oc.env:API_KEY_NAME}` for credentials. The checked-in
    self-hosted examples also read Cloudflare Access values from the environment.

## Validation boundary

Doctor composes the player and provider sequentially, constructs capabilities and identity, then
constructs the Pydantic AI agent. A missing provider credential fails the **Inst.** column. With
`--live`, doctor makes one request and reports the result in **Live**.

[Configure a provider](../../run-and-submit/configure-provider.md)
[Troubleshoot provider access](../../troubleshooting/providers-and-model-responses.md)
