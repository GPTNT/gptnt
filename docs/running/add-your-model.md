# Add your model

One of the first things you'll want to do is add your own model. Under the hood, we use Hydra for all of our configuration. Because we understand that Hydra can be a bit overwhelming, we have a simple CLI wrapper around it to simplify the process _a little_. Unfortunately, editing the YAML file for your model cannot be avoided entirely.

!!! tip
For your ease, we have already provided various configurations beyond what we ran in the leaderboard, in case anyone wants to have a go and see what happens! We still recommend reading this page, especially the section on [providers](#providers) to ensure you can connect to your preferred supplier.

## How it works

We have offloaded all responsibility for running models to [Pydantic AI](https://ai.pydantic.dev/ "https://ai.pydantic.dev/"). Pydantic AI is an excellent library for dealing with the many variations that come with different models and providers. We started using it when it was on v0.0.10 at the very beginning of this project and you should use it. It's brilliant.

!!! warning
We do not (currently) support Pydantic AI v2. There shouldn't be any major issues, but we haven't tested it yet. If you want to use v2, please let us know and we can prioritise that more.

We instantiate everything using dependency inversion through Hydra to keep the `__init__`'s simple and the codebase compositional. This means that the configs in `configs/model` contain everything you need to implement and configure access to your models. There are three main parts to configure:

1. How the model is configured (e.g. temperature, max tokens, etc.)
2. How you access the model
3. What capabilities the model has

## Adding a new model

For your model, you need to create a new file in `configs/model`. Alternatively, you can run the following (replacing `{model-name}` with a unique name for your model):

```bash
gptnt new model <model-name>
```

??? question "Does it matter what it's called?"
No, it does not matter what you call the model. It matters that _you_ know what it is, because you'll need to use that name over and over and over again.

### Configuring model settings

If you look at one of the existing models configs, you'll see that the "model" part (that says what model we will be using) looks like this:

```yaml linenums="1" hl_lines="4 5"
action_predictor:
    agent:
        model:
            _target_: pydantic_ai.models.anthropic.AnthropicModel # (1)!
            model_name: claude-sonnet-4-6 # (2)!

        model_settings:
            _target_: pydantic_ai.models.anthropic.AnthropicModelSettings # (3)!
            _convert_: all
            anthropic_effort: low
            anthropic_thinking:
                type: disabled
```

1. Class for the model from Pydantic AI's models.
2. The name of the model to use.
3. The settings for the model, which are specific to that implementation.
4. Minimising the thinking capabilities of the model. This is important because we don't want the model to "think" about what it is doing using reasoning tokens since we use ReAct.

For the model, we don't just use the simple `provider:model-name` format that Pydantic AI supports because we need to _also_ be able to disable the thinking capabilities of models. (Yes, I know that Pydantic AI v2 makes this easier, but we haven't tested it yet and we don't want to break things for now.)
Each model has a way of disabling its thinking. For now, we need to do things the slightly more difficult way.

1. Find your model in [Pydantic AI's models & providers docs](https://ai.pydantic.dev/models/overview) and update the `_target_` and `model_name` fields accordingly.
    ```yaml linenums="3"
    model:
        _target_: pydantic_ai.models.<provider>.<ModelClass>
        model_name: <model-name>
    ```
2. Find the settings class for your model and update the `_target_` field accordingly.

    ```yaml linenums="7"
    model_settings:
        _target_: pydantic_ai.models.<provider>.<ModelSettingsClass>
        _convert_: all
    ```

    !!! warning "You must set `_convert_: all`."
    If you don't, you'll get a `ValidationError` when you try to run your model.

## Setting the Capabilities

!!! danger "These are not Pydantic AI's Capabilities"
We made this benchmark before Pydantic AI had a capabilities system, so we rolled our own. This means that the capabilities you set here are _not_ the same as Pydantic AI's capabilities. We use these to determine what your model can and cannot do, and to shape the prompts and parse the outputs accordingly. This will likely change in the future, but for now, this is how it works.

Models are "players" of the game. Each player has capabilities—things they can and can't support.

The `capabilities` block at the top of your config is where you tell us what your model is and what it can do. We use it for matchmaking, and the runtime uses it to shape the prompts, the images, and how we parse what comes back. Every field is documented inline in the scaffold, but these are the ones you'll actually reach for:

| Field                            | What it does                                                                                                                   |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `player_name`                    | The name that shows up in specs, rosters, and recordings.                                                                      |
| `thinking_method`                | `thinking-out-loud` (ReAct—the reasoning _is_ the message) or `inner-monologue` (reasoning kept in its own `<think>` section). |
| `structured_output_mode`         | How Pydantic AI coaxes structured output: `null`, `prompted`, `native`, or `tool`.                                             |
| `include_schema_in_instructions` | Whether we paste the output schema into the instructions.                                                                      |
| `interaction_location_method`    | How the model points at things: `set-of-marks` (elements labelled A, B, C…) or `coordinates`.                                  |
| `usage_limits`                   | The per-request input and output token budgets. Set these to your model's real limits.                                         |
| `image_dimensions`               | The size of the images we send. Defaults to the [KTANE settings] override it if your model expects a fixed resolution.         |

[KTANE settings]: ../concepts/ktane.md#resolution

The rest have sensible defaults, so leave them be unless you have a reason not to.

!!! warning "Thinking out loud and structured output don't mix"
If `thinking_method` is `thinking-out-loud`, `structured_output_mode` must be `null`—the reasoning is the output, so there's nowhere to hang a schema. And if you do use `prompted`, then `include_schema_in_instructions` has to be `true`, or the model never sees the schema it's meant to follow. Both are enforced, so you'll hear about it if you get it wrong.

## Providers

!!! abstract "How are you accessing your model"
There are several ways of accessing models. For instance, you could use Microsoft Foundry, Google Cloud, Google Vertex, OpenRouter, or even vLLM.

It comes down to two cases.

**A hosted model on its own provider**—Anthropic, OpenAI, Google—needs nothing extra. The `_target_` model class already knows its endpoint, and Pydantic AI reads the key from that provider's usual environment variable (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and so on).

**Anything else**—a model you host yourself, a vLLM server, or an OpenAI-compatible proxy like Foundry, Vertex, or OpenRouter—needs its own base URL and key. Scaffold a provider for it:

```bash
gptnt new provider <name>
```

Fill in the `base_url` and the key in `configs/model/provider/<name>.yaml`, then point your model at it from the roster in your `run.yaml`:

```yaml
players:
    - model: <model-name>
      provider: <name>
```

!!! tip
Don't paste the key into the YAML. Reference an environment variable instead—the scaffolded provider shows you how.

## Validating you set it up correctly

You can make sure that everything is setup correctly by using the `gptnt doctor` command. This will check that your model is valid and that it can be instantiated correctly.

```bash
gptnt doctor
```

Find your model's row in the output:

```text
Models
  Model        Exists  Inst.  Live   Player       Thinking
  your-model      ✓       ⚠     ⊘     your-model   thinking-out-loud

Infrastructure
  ✓  Game binary            found
  ✗  Redis                  not reachable — run `docker compose up -d`
  ⚠  otel-collector :4318   not reachable (optional)
  ⊘  Display (X)            not required on Darwin
```

**Exists** ✓ means the config parsed; **Inst.** that the model built—a `⚠` there usually just means the API key isn't set, which won't block anything. **Live** stays `⊘` unless you pass `--live` (one real request per model, which costs money). A `✗` is a real failure; `⚠` and `⊘` never block a run.
