# Add a new player

One of the first things you'll want to do is add a model to play the game. Under the hood, GPTNT uses [Hydra](https://hydra.cc/, "https://hydra.cc") for all of its configuration. Hydra can be a bit overwhelming, so there's a simple CLI wrapper around it to simplify the process _a little_. Unfortunately, editing the YAML file for your model cannot be avoided entirely.


!!! tip
    For your ease, various configurations are already provided beyond the ones run for the leaderboard, in case anyone wants to have a go and see what happens! It's still worth reading this page, especially the section on [providers](#providers){data-preview} to ensure you can connect to your preferred supplier.


## Briefly, how it works

Every model is a "player" in the game. What matters is not just the model itself, but also its *capabilities* and how you access it.

All responsibility for running the models themselves has been offloaded to [Pydantic AI](https://ai.pydantic.dev/ "https://ai.pydantic.dev/"). Pydantic AI is an excellent library for dealing with the many variations that come with different models and providers. We started using it when it was on v0.0.10 at the very beginning of this project and you should use it. It's brilliant.

Everything is instantiated using dependency inversion through [Hydra](https://hydra.cc/ "https://hydra.cc"). This is to keep the codebase and its features compositional to facilitate people easily hacking onto it. This means that the configs in `configs/player` contain everything you need to implement and configure access to your models. There are three main parts to configure:

1. How the model is configured (e.g. temperature, max tokens, etc.)
2. How you access the model
3. What capabilities the model has


## Adding a new model (as a player)

To add a new model (or model variant), you need to create a new config file that treats your model as a player in `configs/player`. Alternatively, you can run the following to scaffold a new config file (`configs/player/<player-name>.yaml`) for your player (make sure to replace `<player-name>`):

```bash
gptnt new player <player-name>
```

???+ example "Example scaffolds"

    Below are some examples of what the scaffolding would look like if you're instantiating a closed-source model or an open-source model that you're self-hosting with vLLM.

    === "Claude Sonnet 5"

        ```yaml title="configs/player/claude-sonnet-5.yaml"
        # @package player
        #
        # Model profile for "claude-sonnet-5".
        # Every field is documented inline; uncomment and edit as needed.

        defaults:
          - _self_

        # --- Identity -----------------------------------------------------------
        identity:
          # Information we use if you submit to the leaderboard
          display_name: Claude Sonnet 5
          organisation: Anthropic
          url: https://anthropic.com/claude/sonnet
          is_os_model: false

        # --- Capabilities -----------------------------------------------------------
        # What this player is and what it can do. The Experiment Manager uses this for
        # matchmaking; the runtime uses it to shape prompts, images and output parsing.
        capabilities:
          # Name for this player in specs, rosters and recordings.
          player_name: claude-sonnet-5 # (1)!

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
            input_tokens_limit: 872000
            output_tokens_limit: 128000

        action_predictor:
          agent:
            model:
              _target_: pydantic_ai.models.anthropic.AnthropicModel
              model_name: claude-sonnet-5 # (2)!
            model_settings:
              thinking: false
        ```

        1. The name of the player, which is used in the run manifest and in the results.
        2. The name of the model itself, from [`AnthropicModelName`][pydantic_ai.models.anthropic.AnthropicModelName] in Pydantic AI. This is the name that Pydantic AI uses to instantiate the model.

    === "GLM-5.2 (self-hosting with vLLM from Hugging Face)"

        ```yaml title="configs/player/glm-5-2.yaml"
        # @package player
        #
        # Model profile for "glm-5-2".
        # Every field is documented inline; uncomment and edit as needed.

        defaults:
          - _self_

        # --- Identity -----------------------------------------------------------
        identity:
          # Information we use if you submit to the leaderboard
          display_name: GLM-5.2
          organisation: Z.ai
          url: https://huggingface.co/zai-org/GLM-5.2
          is_os_model: true


        # --- Capabilities -----------------------------------------------------------
        # What this player is and what it can do. The Experiment Manager uses this for
        # matchmaking; the runtime uses it to shape prompts, images and output parsing.
        capabilities:
          # Name for this player in specs, rosters and recordings.
          player_name: glm-5-2 # (1)!

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
            input_tokens_limit: 999000
            output_tokens_limit: 1000 # (2)!

        action_predictor:
          agent:
            model:
              _target_: pydantic_ai.models.openai.OpenAIChatModel # (3)!
              model_name: my-v-nice-glm-model # (4)!
            model_settings:
              _target_: pydantic_ai.models.openai.OpenAIChatModelSettings
              _convert_: all
              max_tokens: 1000
        ```

        1. The name of the player, which is used in the run manifest.
        2. GLM-5.2 supports 1M tokens in total, and we limit the output tokens to 1k because models don't really need more than that. So we can use as many as possible for the input.
        3. The model class is [`pydantic_ai.models.openai.OpenAIChatModel`][pydantic_ai.models.openai.OpenAIChatModel] because we are using vLLM to serve the model, which is compatible with the OpenAI API.
        4. When using vLLM, we can name the model whatever we want in the server, so we can set it to `my-v-nice-glm-model` here. This is the name that vLLM will use to serve the model, and it is *not* the same as the name of the player.

!!! warning "You DO NOT need to create separate player configs for Defuser and Expert."
    One model, one player. That's it! You set up how many instances of a given player (model) you need in [Run your model](run-your-model.md){data-preview}, where the benchmark assigns each instance its role.

### Choosing a name for your player

The name for the player appears in two key places: the name of the file (`configs/player/<player-name>.yaml`) and the `player_name` in the `capabilities` block of the config. The name of the file is used to identify your player in the run manifest, and the `player_name` is used to identify your player in the results. **They should be the same.**

!!! question "Does it _really_ matter what it's called?"
    No, it does not matter what you call the model. It matters that _you_ know what it is, because you'll need to use that name over and over and over again. If you are not going to be submitting to the leaderboard, then you definitely do not need to worry about picking the right name.


You want to pick a name that makes it easier to identify and compare players when it comes to submitting on the leaderboard. For simplicity, there are (likely) two ways for naming your player, depending on where it's from.

#### Using the name from Pydantic AI

If you are using a model that can be accessed from a provider API, you can use the name from Pydantic AI. For instance, you can find:

- Anthropic at [`pydantic_ai.models.anthropic.AnthropicModelName`][pydantic_ai.models.anthropic.AnthropicModelName]
- OpenAI at [`pydantic_ai.models.openai.OpenAIModelName`][pydantic_ai.models.openai.OpenAIModelName]
- Google at [`pydantic_ai.models.google.GoogleModelName`][pydantic_ai.models.google.GoogleModelName]


??? example "What about Bedrock, Groq, etc.?"
    These are providers. While they have specific requirements for accessing models, they are not creating the models themselves. You should use the name of the actual model as the name of your player, and not the provider. For instance, if you are accessing Claude Sonnet 4.6 through Bedrock, the name of the player should be `claude-sonnet-4-6`, and not `bedrock:us.anthropic` or `bedrock`.

#### Using the name from Hugging Face

If you are using an open-weight model from Hugging Face, you can use the name from the Hugging Face model hub. Similar to the above, you must remove the prefix. For example, if the model name is `Qwen/Qwen3.5-27B`, you would use `qwen3-5-27b` as the name of your model (ignoring everything before the `/`, replacing punctuation with dashes and using lower case).

!!! warning
    You must replace punctuation with a dash (`-`) and make it all lowercase. This is because the model name is used in the path of the submission, and we want to avoid any issues with special characters.


### Configuring the identity

On top of choosing the name, you can add identity metadata for the player. GPTNT does not use this block to run the model; it is only used when [submitting to the leaderboard](../submit-your-results.md){data-preview}, so the submission can show the model's display name, organisation, URL, and whether it is open-source.

=== "Closed-source model (e.g., Sonnet 5)"

    ```yaml
    identity:
      # Information we use if you submit to the leaderboard
      display_name: Claude Sonnet 5
      organisation: Anthropic
      url: https://anthropic.com/claude/sonnet
      is_os_model: false

    capabilities:
      player_name: claude-sonnet-5 # (1)!
    ```

    1. `player_name` is different to the display name.

=== "Open-source model (e.g., Qwen 3.5)"

    ```yaml
    identity:
      # Information we use if you submit to the leaderboard
      display_name: Qwen 3.5 (27B)
      organisation: Qwen
      url: https://huggingface.co/Qwen/Qwen3.5-27B
      is_os_model: true

    capabilities:
      player_name: qwen3-5-27b  # (1)!
    ```

    1. `player_name` is different to the display name.


### Configuring a model

If you look at one of the existing model configs, you'll see that the "model" part (that says which model will be used) looks like this:

```yaml linenums="1"
action_predictor:
  agent:
    model:
      _target_: pydantic_ai.models.anthropic.AnthropicModel # (1)!
      model_name: claude-sonnet-4-6 # (2)!

    model_settings: # (3)!
      thinking: false # (4)!
```

1. The model class, [`pydantic_ai.models.anthropic.AnthropicModel`][pydantic_ai.models.anthropic.AnthropicModel]
2. The official ID of the model to use. Feel free to reuse the `model_name` as the `player_name`.
3. The model settings, which can be the generic ones, or more specific.
4. Turn the model's own reasoning off. [`thinking`][pydantic_ai.settings.ModelSettings.thinking] is a setting that works across every model. GPTNT uses ReAct-style reasoning that lives in the output itself, so there's no point the model spending reasoning tokens on top of it.


There are several footguns here that you need to be aware of.

#### Choose the right model class

The model class is important otherwise you won't instantiate the right model. Pydantic AI has a nice way to help with it, as it fails to instantiate if you do not use the right class with the right model name. Don't you just love Pydantic?

???+ note "How to use a self-hosted model"
    If you are hosting the model yourself, you will need to use something like [vLLM](https://vllm.ai/) or [SGLang](https://www.sglang.io/) to serve it. These inference engines are compatible with the OpenAI API and to access it: you can use either [`pydantic_ai.models.openai.OpenAIChatModel`][pydantic_ai.models.openai.OpenAIChatModel] or [`pydantic_ai.models.openai.OpenAIResponsesModel`][pydantic_ai.models.openai.OpenAIResponsesModel] for vLLM, and [`pydantic_ai.models.openai.OpenAIChatModel`][pydantic_ai.models.openai.OpenAIChatModel] for SGLang.

    Importantly, **you need to specify a provider** for this model in the model config. Providers are discussed [later](#providers){data-preview} in more detail, but this is incredibly important for running your own model. When serving (e.g., running `vllm serve`), it hosts a web server that will accept your requests and run them as fast as possible. **You must update the `base_url`** with the URL of your server, and provide the API key if you are using one. Understanding how serving models works is outside the scope of this benchmark, but you can learn more from the docs of your chosen engine.

    <a id="example-model-config"></a>

    ```yaml title="Example model config" hl_lines="7 8 9"
    agent:
      model:
        _target_: pydantic_ai.models.openai.OpenAIChatModel # (1)!
        model_name: my-model # (2)!
      model_settings:
        max_tokens: 1000
      provider:
        _target_: pydantic_ai.providers.openai.OpenAIProvider # (3)!
        base_url: http://<url>/v1 # (4)!
    ```

    1. The model class, [`pydantic_ai.models.openai.OpenAIChatModel`][pydantic_ai.models.openai.OpenAIChatModel]
    2. This is the name that your inference engine uses to serve the model, so you can set it yourself.
    3. The provider class, [`pydantic_ai.providers.openai.OpenAIProvider`][pydantic_ai.providers.openai.OpenAIProvider]
    4. The base URL of your inference engine. This is the URL that you use to access the model. For example, if you are using vLLM, it will be `http://localhost:8000/v1` if you are running it locally.


#### Disable reasoning tokens

[`thinking`][pydantic_ai.settings.ModelSettings.thinking] controls how much the model generates reasoning tokens.[^1] `false` turns it off, and `'minimal'`, `'low'`, `'medium'`, `'high'`, or `'xhigh'` turn it on at that effort.

[^1]: You can think of this as a variation of the thinking budget/token budget that used to be used a setting for older LLMs. With this, you are basically telling models to think for some amount of time. Nobody knows how much time or how many tokens, but it's some time.

!!! danger "Always-on reasoning models"
    Some models always reason and ignore `false`. Set `thinking: 'minimal'` to keep it as low as it goes. Check the documentation for your model to see if it has any special settings for reasoning. If it does, you can use those instead of `thinking` to control the reasoning.

!!! danger "This will not affect open source models that you are serving with vLLM or SGLang"
    Please check the settings for your respective model. It is unlikely but possible that you may have to provide a custom chat template to achieve this, which we had to do for InternVL3.5.

???+ note "Using model-specific settings classes needs `_convert_: all`"

    [`ModelSettings`][pydantic_ai.settings.ModelSettings] is the generic settings class that works across all models. It has a few fields that are common to all models, like [`thinking`][pydantic_ai.settings.ModelSettings.thinking], [`max_tokens`][pydantic_ai.settings.ModelSettings.max_tokens], and [`temperature`][pydantic_ai.settings.ModelSettings.temperature].

    Some models have their own settings which are not part of the generic `ModelSettings`. In these situations, you need to provide a `_target_` for the class and set `_convert_: all` on the `model_settings` block. Otherwise, you'll get a `ValidationError` when you try to run your model.

#### Disabling safety settings

This benchmark uses the word "bomb" a lot. Some APIs have safety settings that will block the model from receiving or generating content that contains certain words. If your model has safety settings and you don't disable them, you will get a lot of false-positive errors.

??? example "Example: Google's safety settings"
    Pydantic AI has a [`GoogleModelSettings`][pydantic_ai.models.google.GoogleModelSettings] class that allows you to control the safety settings. This is what we did for Gemini 3.

    ```yaml title="configs/player/gemini-3-flash-preview.yaml"
    action_predictor:
      agent:
        model:
          _target_: pydantic_ai.models.google.GoogleModel
          model_name: gemini-3-flash-preview

        model_settings:
          _target_: pydantic_ai.models.google.GoogleModelSettings
          _convert_: all
          thinking: false
          google_video_resolution: "MEDIA_RESOLUTION_MEDIUM"
          google_safety_settings:
            - category: HARM_CATEGORY_HARASSMENT
              threshold: BLOCK_NONE
            - category: HARM_CATEGORY_DANGEROUS_CONTENT
              threshold: BLOCK_NONE
            - category: HARM_CATEGORY_HATE_SPEECH
              threshold: BLOCK_NONE
            - category: HARM_CATEGORY_SEXUALLY_EXPLICIT
              threshold: BLOCK_NONE
            - category: HARM_CATEGORY_CIVIC_INTEGRITY
              threshold: BLOCK_NONE
    ```

??? example "Guardrails from Azure's OpenAI service"
    Sometimes, the guardrails are on by default and are only controlled in the UI of your provider. For instance, Azure's OpenAI service (at the time of writing/when we ran the initial benchmark) had [guardrail classifiers that were on by default](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/default-safety-policies) and could only be changed in the Azure portal. It is not possible to disable them entirely [without approval](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/content-filters), but you can create a content policy that will set them to low. Unfortunately, [this is not perfect]("need to add how we handle this") but we found that it is needed.

## Providers

There are several ways of accessing models. For instance, you could use Microsoft Foundry, Google Cloud, Google Vertex, OpenRouter, or even vLLM. Simply put, it comes down to two cases:

### Using the default provider

If you are using a model and accessing it through the default provider, then you don't need to do anything else. The model class from Pydantic AI will automatically load the default provider and try to read the API key, and will complain if it cannot find one. For instance, if you are using `pydantic_ai.models.anthropic.AnthropicModel`, it will automatically use the Anthropic provider and read the key from the `ANTHROPIC_API_KEY` environment variable.

### Using another provider

If you're accessing a model through a different provider (e.g., Bedrock, Groq, OpenRouter, Vertex, vLLM, etc.), then you need to tell Pydantic AI how you are going to be connecting to the model. Similar to creating a new player, you can scaffold a new provider config file in `configs/player/provider`:

```bash
gptnt new provider <name>
```

The result of this _is_ going to be a bit more customised and personal. If you're using another provider, here's an example workflow:

1. Find the provider class in [Pydantic AI](https://pydantic.dev/docs/ai/models/overview/). For instance, if you're using OpenRouter, you would use [`pydantic_ai.providers.openrouter.OpenRouterProvider`][pydantic_ai.providers.openrouter.OpenRouterProvider]. Or if you want to use [Anthropic models through Microsoft Foundry](https://pydantic.dev/docs/ai/models/anthropic/#microsoft-foundry).
2. Update the `_target_` in the scaffolded provider config file to point at the provider class and ensure that the various parameters are setup correctly.
3. Verify it is configured correctly with the `gptnt doctor` command.
4. Choose that provider in your run config by setting `provider` on a player entry. We explain this in more detail in [Run your model](run-your-model.md){data-preview}.

!!! note
    If you know Hydra, this process will be simpler and self-explanatory. If you don't know Hydra, then it will be a bit more confusing. The important thing is to make sure that the `_target_` is pointing at the right provider class and that the parameters are setup correctly.

??? question "Why a separate file for providers?"
    The provider is kept separate from the model because you may want to run multiple models on the same provider, or the same model on different providers. This way, you can change the provider without having to change the model config file, or have several model configs.

??? question "What about self-hosting?"
    [Above](#example-model-config){data-preview}, we provide an example of including the provider within the model config itself. You _can_ do that, but it's best avoided. Use a provider config file for your self-hosted model too, as it makes it easier to change the provider without having to change the model config file, or have several model configs. It also makes it easier to share your model config with others, because they can use their own provider config file.

## Setting the Capabilities

!!! danger "These are not Pydantic AI's Capabilities"
    We made this benchmark before Pydantic AI had a capabilities system, so we rolled our own. This means that the capabilities you set here are _not_ the same as Pydantic AI's capabilities. We use these to determine what your model can and cannot do, and to shape the prompts and parse the outputs accordingly. This will likely change in the future, but for now, this is how it works.

Models are "players" of the game. Each player has capabilities—things they can and can't support.

The `capabilities` block at the top of your config is where you say what your model is and what it can do. It's used for matchmaking, and the runtime uses it to shape the prompts, the images, and how the output is parsed. Every field is documented inline in the scaffold, but these are the ones you'll actually reach for:

| Field | What it does | Default |
| ----- | ------------ | ------- |
| `player_name` | The name that shows up in specs, rosters, and recordings. | Required |
| `thinking_method` | How the model reasons:<br>`thinking-out-loud` means ReAct-style reasoning is part of the message.<br>`inner-monologue` keeps reasoning in a dedicated `<think>` section. | `inner-monologue` |
| `structured_output_mode` | How Pydantic AI coaxes structured output:<br>`null`, `prompted`, `native`, or `tool`. | `prompted` |
| `include_schema_in_instructions` | Whether the output schema is pasted into the instructions. | `true` |
| `interaction_location_method` | How the model points:<br>`set-of-marks` labels elements A, B, C, ...<br>`coordinates` asks for pixel or normalised coordinates. | `set-of-marks` |
| `usage_limits` | The per-request input and output token budgets. Set these to your model's real limits. | none |
| `image_dimensions` | The size of the images that get sent. Override it if your model expects a fixed resolution. | 640×480 |
| `preserve_last_frame_for_n_turns` | How many previous turns' final frames are provided. | 0 |
| `enable_nobf_generation` | Whether models should receive a warning when their previous output caused an error. | `true` |

!!! warning "Thinking out loud and structured output don't mix"
    If `thinking_method` is `thinking-out-loud`, `structured_output_mode` must be `null`—the reasoning is directly included in the output so you cannot enforce the structured output schema.[^why-not-structured] And if you do use `prompted`, then `include_schema_in_instructions` has to be `true`, or the model never sees the schema it's meant to follow. Both are enforced, so you'll hear about it if you get it wrong.

[^why-not-structured]: Using structured outputs was something we wanted to do for the benchmark. But JSON Schema does not enforce the order in which keys are generated by models. This is important because we wanted to ensure models were reasoning _before_ deciding their action, otherwise they would rationalise their actions after-the-fact.

??? question "What to do if you are not sure what to pick?"
    If you are not sure, just leave the defaults. They have been set to the same values as the initial GPTNT benchmark, so that will ensure that your model is compatible.



### Capabilities have fingerprints

Capabilities are incredibly important for comparing models together. We want to know if two models are using the same capabilities, or if two models are interacting and reasoning differently. This is because changing the capabilities can drastically change the results. As shown in the [GPTNT paper](https://arxiv.org/abs/2606.28514), changing the action space from set-of-marks to coordinates can affect models' ability to play the game.


## Finding out how many tokens per image

One of the biggest footguns is that we send images to the model, and we try to make sure that the model has enough tokens to process the input we are about to give it. The number of tokens per image depends on the model and the image size. To ensure that the number is calculated correctly, run:

```bash
gptnt measure-tokens-per-image <player-name> # (1)!
```

1. This uses Hydra under the hood. Replace `<player-name>` with the file name of your config in `configs/player/` (without the `.yaml` extension). For instance, if your config is `configs/player/claude-sonnet-5.yaml`, you would run `gptnt measure-tokens-per-image claude-sonnet-5`.

This command will use the capabilities you have already setup, especially for the image dimensions. If you have not provided any, it uses the default image dimensions of 640×480. It will then send two requests to the model: one request send a short text prompt to elicit a short response _with the image_, and the second sends the same text prompt _without the image_. The difference in the number of input tokens is the number of tokens that image takes up.

The config file is automatically updated with the correct number of tokens per image, so you don't have to do anything else. If you change the image dimensions, you can run this command again.




## Validating you set it up correctly

You can make sure that everything is setup correctly by using the `gptnt doctor` command. This will check that your model is valid and that it can be instantiated correctly.

```bash
gptnt doctor
```

Find your model's row in the output:

```text
Models
  Model        Exists  Inst.  Live   Player       Thinking
  your-model      ✓       ✗     ⊘     your-model   thinking-out-loud

Infrastructure
  ✓  Game binary            found
  ✗  Redis                  not reachable — run `docker compose up -d`
  ⚠  otel-collector :4318   not reachable (optional)
  ⊘  Display (X)            not required on Darwin
```

**Exists** ✓ means the config parsed; **Inst.** ✓ means that the model built. **Live** stays `⊘` unless you pass `--live` (one real request per model, which costs money) it sends a small request to a model and checks that you get a response, in which case you get a ✓ here. A `✗` is a real failure; `⊘` never blocks a run.
