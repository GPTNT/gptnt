<div align='center'>

# GPTNT

_Can two AI agents talk each other through defusing a bomb?_

Two AI agents must play the roles of _Defuser_ and _Expert_ in [_Keep Talking and Nobody Explodes_ (KTANE)](https://keeptalkinggame.com). The Defuser sees the bomb, the Expert reads the manual, and they must communicate in real-time to defuse it.

</div>

## Links

- [Website](https://gptnt.github.io)
- [Paper](https://arxiv.org/)
- [Leaderboard](https://gptnt.github.io)
- Usage Guide (actively working on it)
- [Quickstart](#quickstart)

## Summary

GPTNT is an AI benchmark built on **KTANE** ("Keep Talking and Nobody Explodes"): a co-op bomb-defusal game where a _Defuser_ who can see the bomb and an _Expert_ who can read the manual must talk to each other to defuse it. Here, the players are AI models. You run **experiments** that pair models against bombs and record how well they do. The job of this repo is to generate those experiments, run them, and collect the results.

> [!NOTE]
> Creating a asynchronous, real-time, multi-agent benchmark is not trivial. We've tried to make the process of running things as simple and clear as possible to ensure that no logs or information is lost in the async hell that can happen. You can find more details about various aspects of the benchmark and codebase in the [docs/](docs/).

## Preconditions

### 1. The KTANE game binary (you supply this)

The game is **not** distributed here and **not** provisioned by any command. You must supply it yourself. You can purchase it from the [Humble Bundle store](https://humblebundle.com/store/keep-talking-and-nobody-explodes).

Copy-paste your platform's KTANE build under `storage/ktane`. This path is included in the `.gitignore`.
It is discovered by `src/gptnt/ktane/executable.py` (`get_executable_path`), which raises `GameNotFoundError` if it cannot find one.

| OS      | Expected layout under `storage/ktane`     |
| ------- | ----------------------------------------- |
| Linux   | `*.x86_64` plus a `ktane_Data/` directory |
| macOS   | `*.app/Contents/MacOS/<exe>`              |
| Windows | `*.exe`                                   |

### 2. Docker (infra)

> [!important]
> Docker is only used to run Redis and the OpenTelemetry collector. The game itself is **not** run in Docker.

We use Redis as a message bus between the various services and the players. You can find out more about why we use Redis in the [why-redis.md](docs/why-redis.md) document.

In addition, we also use an OpenTelemetry collector to collect traces from the various services and send them to [Logfire](https://logfire.pydantic.dev/) (or another backend). This is important for debugging and understanding what is happening in the system—more in [docs/how-to-observability.md](docs/how-to-observability.md).

```bash
docker compose up -d
```

### 3. A display (Linux only)

The game has to render somewhere.

- **macOS / Windows:** nothing to do.
- **Linux with a desktop session:** if `$DISPLAY` is already set, the game uses it — nothing to do.
- **Linux, headless:** start a GPU-backed Xorg with `scripts/startx.py`, then either export `$DISPLAY` for the run to inherit, or name the display(s) in the run manifest (`displays: [N]`, one per GPU to spread rooms across GPUs).

> [!TIP]
> If you need to use sudo and you still want to use uv/similar, you can use `sudo -E` to preserve the environment variables. For instance, to run an X display on display 3, you can run:
>
> ```bash
> sudo -E .venv/bin/python scripts/startx.py 3
> ```

### 4. Keys (if you are running a model)

During development, we use [mise-en-place](https://mise.jdx.dev) to manage the toolchain and secrets. It reads keys from `mise.local.toml` (git-ignored) or your shell environment. Feel free to do what you want, but you'll need to set the provider API keys (and also WandB credentials if you want to aggregate results there).

Ours looks like this:

```toml
# mise.local.toml
[env]
ANTHROPIC_API_KEY = "sk-..."
WANDB_API_KEY = "..."
WANDB_ENTITY = "your-entity"
WANDB_PROJECT = "your-project"
LOGFIRE_TOKEN = "..." # only needed for the prod observability profile
```

Which keys you need depends on which models you run:

- **A provider API key** for whatever model(s) you use (e.g. `ANTHROPIC_API_KEY`). This project constructs models through **pydantic-ai**, so the authoritative list of "which env var does provider X need" is pydantic-ai's own [models & providers docs](https://ai.pydantic.dev/models/). Anything pydantic-ai can build, this project can use.
- **WandB credentials** (`WANDB_API_KEY`, `WANDB_ENTITY`, `WANDB_PROJECT`) to record results. The run's `recording.wandb` setting reads `WANDB_ENTITY` / `WANDB_PROJECT` from the env (set `wandb: auto` in your `run.yaml`).
- **`LOGFIRE_TOKEN`** only for the prod observability profile.

## Quickstart

Once you have everything in place (KTANE binary, infrastructure, etc.), you can run a benchmark end-to-end with a single command.

We've started you off with a `runs/quickstart.yaml` manifest that declares a simple run: one room, two dummy players that do not spend money (don't expect them to succeed), and some experiments.

```bash
# 1. Install the toolchain (python 3.13, uv) — see https://mise.jdx.dev
mise install

# 2. Install dependencies (runs `uv sync --all-groups`)
mise run install

# 3. Start INFRA ONLY (redis + redis UI + otel-collector).
docker compose up -d

# 4. Verify the whole setup BEFORE running anything
uv run gptnt doctor runs/quickstart.yaml
```

Then run the benchmark from a manifest:

```bash
uv run gptnt run runs/quickstart.yaml
```

`gptnt run` is conditioned on the `doctor` command being successful. It then spawns the experiment manager, game rooms, and players, submits the generated experiment specs to the experiment manager, and streams progress until the run finishes. If you have a display, you should see the game window pop up and it start to do things. If you don't have a display, the game will run headless and you can watch the logs.

> [!TIP]
> If you have an activated virtualenv you can drop the `uv run` prefix and just call `gptnt ...`.

## Citation

```bibtex
@misc{gptnt,
      title={GPTNT: Benchmarking Real-Time Collaboration Between Multimodal Agents on Keep Talking And Nobody Explodes},
      author={Amit Parekh and Sabrina McCallum and Kareem Al-Hasan and Malvina Nikandrou and Alessandro Suglia and Ioannis Konstas},
      year={2026},
      eprint={2606.28514},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2606.28514},
}
```

## License

This benchmark is licensed under the terms of the license found in [LICENSE](LICENSE).
