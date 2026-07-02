"""Fully-commented config templates rendered by the `gptnt new` commands.

Render with `TEMPLATE.replace("<NAME>", name)`.
"""

PLAYER_TEMPLATE = """# @package player
#
# Player profile for "<NAME>".
# Every field is documented inline; uncomment and edit as needed.

defaults:
  - _self_

# --- Capabilities -----------------------------------------------------------
# What this player is and what it can do. The Experiment Manager uses this for
# matchmaking; the runtime uses it to shape prompts, images and output parsing.
capabilities:
  # Name for this player in specs, rosters and recordings.
  player_name: <NAME>

  # How the model reasons:
  #   thinking-out-loud -> ReAct-style; reasoning is part of the message (no structured output)
  #   inner-monologue   -> reasoning kept separate from the user-visible message (e.g. parsed as `ThinkingPart` from the model output; the prompt format uses a dedicated `<think>` section).
  thinking_method: thinking-out-loud

  # Structured output mode (pydantic-ai). MUST be null when thinking-out-loud.
  # Options: null | prompted | native | tool   (see pydantic-ai StructuredOutputMode)
  structured_output_mode: null

  # Include the output schema in the instructions (required when mode == prompted).
  include_schema_in_instructions: true

  # How the model points at on-screen elements:
  #   set-of-marks -> elements are labelled (A, B, C...) and it replies with a label
  #   coordinates  -> it replies with pixel / normalised coordinates
  interaction_location_method: set-of-marks

  # Per-request token budget. Set these to your model's real limits.
  usage_limits:
    input_tokens_limit: 200000
    output_tokens_limit: 64000

  # Vision input size. Defaults to KTANE settings; override for models with a fixed expected
  # resolution (e.g. some open-weights VLMs).
  # image_dimensions:
  #   _target_: gptnt.common.image_ops.ImageDimensions
  #   width: 640
  #   height: 480

# --- Model ------------------------------------------------------------------
action_predictor:
  agent:
    # Option 1 (recommended): a pydantic-ai model string "<provider>:<model-name>".
    # The provider class + default endpoint are inferred and the API key is read
    # from that provider's standard env var (e.g. ANTHROPIC_API_KEY). Full list:
    # https://ai.pydantic.dev/models/
    model: anthropic:claude-sonnet-4-6

    # Option 2 (custom endpoint/self-hosted/vLLM): a bare string can't carry a
    # base_url, so use the explicit form below AND attach an endpoint with
    # `gptnt new provider <name>`, then set `provider: <name>` on this player's
    # entry in your run.yaml `players:` list. Comment out the Option 1 line above.
    # model:
    #   _target_: pydantic_ai.models.openai.OpenAIChatModel
    #   model_name: <your-served-model-name>

    # Option 3 (model settings): `thinking` controls the model's own reasoning, unified across
    # providers. GPTNT scores ReAct-style reasoning in the message, so this defaults it off.
    #   false                                  -> disable (omitted for models already off by default)
    #   'minimal'/'low'/'medium'/'high'/'xhigh' -> enable at that effort
    # An always-on reasoning model (e.g. gpt-5.x, gemini-3) ignores false; floor it with 'minimal'.
    # model_settings:
    #   thinking: false
    #
    # Provider-only fields (e.g. Google safety settings) need that provider's settings class, with
    # `thinking` set on it instead of the provider-specific reasoning field:
    # model_settings:
    #   _target_: pydantic_ai.models.google.GoogleModelSettings
    #   _convert_: all
    #   thinking: false
    #   google_safety_settings: [...]
"""


PROVIDER_TEMPLATE = """# @package player.action_predictor.agent.model
#
# Endpoint override for "<NAME>".
# Used to attach a custom provider (base_url + key) to whichever model selects it. Also used for
# self-hosted/vLLM/OpenAI-compatible proxies.
#
# Attach it via the `provider:` field on a player's run.yaml players entry, e.g.:
#   players: [{player: <player>, provider: <NAME>}]
# The player config it attaches to should use the explicit (Option 2) `_target_` form.

provider:
  # OpenAI-compatible provider is the common case (vLLM, LM Studio, many proxies).
  # For other backends (Anthropic/Google/Azure/Bedrock/...), swap this
  # _target_ — see https://ai.pydantic.dev/models/ for the provider classes.
  _target_: pydantic_ai.providers.openai.OpenAIProvider

  # Endpoint base URL (include the trailing /v1 for OpenAI-compatible servers).
  base_url: https://your-endpoint.example/v1

  # API key. Prefer an env var (mise-managed) over hard-coding!!!!!! But if you need to...
  # api_key: ${oc.env:YOUR_ENDPOINT_API_KEY}
"""
