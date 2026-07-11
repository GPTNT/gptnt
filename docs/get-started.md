# Get Started

Creating an asynchronous, real-time, multi-agent benchmark is not trivial. We've tried to make the process of running things as simple and clear as possible to ensure that no logs or information is lost in the async hell that can happen.




## Preconditions

There are some things we cannot provide for you through Python dependencies so you need to run them yourself. We've tried to keep them to a minimum.

### Bring your own game

!!! danger "You must provide the game yourself"
    We do **not** distribute or provide the game—you must supply it yourself. You can purchase a DRM-free version from the [Humble Bundle store](https://humblebundle.com/store/keep-talking-and-nobody-explodes).

Copy-paste your KTANE game that you downloaded under `storage/ktane`.[^game-path] It is discovered by `src/gptnt/ktane/executable.py` (`get_executable_path`), which raises `GameNotFoundError` if it cannot find one.

| OS      | Expected layout under `storage/ktane`     |
| ------- | ----------------------------------------- |
| Linux   | `*.x86_64` plus a `ktane_Data/` directory |
| macOS   | `*.app`[^funny-vscode]                    |
| Windows | `*.exe`                                   |

[^game-path]: This path is included in the `.gitignore` so it won't get committed.
[^funny-vscode]: If you are using VSCode, it may show the `*.app` bundle as a folder. This is normal and expected so there's nothing to worry about. It's just how `*.app` files work.

### Run the infrastructure (with Docker Compose)

!!! note
    Docker is only used to run Redis and the OpenTelemetry collector. The game itself is **not** run in Docker.

We use Redis as a message bus between the various services and the players.

<!-- You can find out more about why we use Redis in the [why-redis.md](why-redis.md) document. -->

In addition, we also use an OpenTelemetry collector to collect traces from the various services and send them to [Logfire](https://logfire.pydantic.dev/) (or another backend).

<!-- This is important for debugging and understanding what is happening in the system—more in [Observability]("Coming soon"). -->

Run the following command to start Redis and the OpenTelemetry collector:

```bash
docker compose up -d
```

??? question "What if you don't have Docker?"
    If you don't have Docker, you can just run Redis yourself. The default configuration is to listen on `localhost:6379` with no password. Check the `docker-compose.yml` file for the exact configuration to copy from.

??? question "Why no password for Redis?"
    We don't use a password for Redis because it is only accessible from the local machine and there was no one else using the machine and nothing else running on it. Of course, the correct thing to do, especially if you are accessing Redis remotely, is to **set a password and configure the services to use it.**

??? question "What if you don't want to use OpenTelemetry?"
    The most robust option is to set the `COMPOSE_PROFILES` environment variable to `dev` to send all traces to the void. Not using OpenTelemetry will make deubugging harder, so we recommend you keep it enabled unless you know you don't need it.

### Rendering the game: display vs headless

The game has to render _somewhere_. If you have a display, like on macOS or Windows, you don't need to do anything. If you are on Linux, you may need to start an X display.

!!! warning "The game must run on a machine that can render graphics"
    KTANE is a Unity game. The machine that runs the game needs a working graphics/display stack: for example, a normal desktop/laptop display, a workstation GPU such as an NVIDIA RTX card, or a headless Linux machine with Xorg backed by a graphics-capable GPU.

    This is separate from the GPU you might use for model inference. Common ML accelerator machines with A100, H100, TPU, or similar compute-focused hardware are often configured for batch/model workloads only and may not be able to back an X display for the game. If your model runs on that kind of machine, run KTANE on a graphics-capable machine and point your player config at the remote model endpoint instead.

    When the game machine and model machine are different, the game-running machine must be able to reach the model server's API. That can be a private network address, a VPN, SSH port forwarding, or a tunnel. In our setups, Cloudflare Tunnel has been a convenient way to expose a self-hosted vLLM endpoint as an HTTPS `base_url`.

We have validated the following cases:

- **macOS/Windows:** nothing to do.
- **Linux with a desktop session:** if `$DISPLAY` is already set, the game uses it—nothing to do.
- **Linux, headless:** start a GPU-backed Xorg with `scripts/startx.py`, then either export `$DISPLAY` for the run to inherit, or name the display(s) in the [run manifest](running/run-your-model.md#displays){data-preview}.

??? tip "How to run a headless X display on Linux"
    If you need to use sudo and you still want to use uv/similar, you can use `sudo -E` to preserve the environment variables. For instance, to run an X display on display 3, you can run:

    ```bash
    sudo -E .venv/bin/python scripts/startx.py 3
    ```

## Run the benchmark (using dummy models)

To make sure that you can run the game and the benchmark, we have "dummy models" that you can run. They don't do anything useful, but they will make sure that the game and the benchmark are working end-to-end.

=== "With `mise` (recommended)"

    ```bash
    # 1. Install the toolchain
    mise install

    # 2. Install dependencies
    mise run sync # (1)!

    # 3. Run Redis and OTEL Collector (if not running)
    docker compose up -d # (2)!

    # 4. Verify your setup works
    gptnt doctor runs/quickstart.yaml

    # 5. Run the benchmark with the dummy models
    gptnt run runs/quickstart.yaml
    ```

    1. Runs `uv sync --all-groups` to install dependencies. All tasks are defined in `mise.toml` so you can check them yourself.
    2. Obviously, you can skip this if you already have Redis and the OpenTelemetry collector running.

=== "Without `mise`"

    ```bash
    # 1. Find out what tools we used from the `mise.toml` file and install them.


    # 2. Install dependencies
    uv sync --all-groups

    # 3. Run Redis and OTEL Collector (if not running)
    docker compose up -d # (1)!

    # 4. Verify your setup works
    gptnt doctor runs/quickstart.yaml

    # 5. Run the benchmark with the dummy models
    gptnt run runs/quickstart.yaml
    ```

    1. Obviously, you can skip this if you already have Redis and the OpenTelemetry collector running.

??? tip "What is `mise`?"
    During development, we use [mise-en-place](https://mise.jdx.dev) to manage the toolchain and secrets. It simplifies the installation of python versions, uv versions, and other tool dependencies. It also manages environment variables and secrets for you. You can use it if you want, but it is not required.

??? info "What does `gptnt run` do?"
    `gptnt run` is conditioned on the `doctor` command being successful (so technically you don't need to explicitly run it separately).
    It then spawns the experiment manager, game "rooms", and players, submits the generated experiment specs to the experiment manager, and streams progress until the run finishes.
    If you have a display, you should see the game window pop up and it start to do things. If you don't have a display, the game will run headless and you can watch the logs.

## Versioning Policy

Since this is a benchmark _and_ a library, it is incredibly important that models are compared on an equal footing, but also that we are not constantly breaking or gating results on new versions. From this, we have a 2-tier versioning policy: one for the codebase, and one for the benchmark.

### Codebase versioning

The codebase follows [Semantic Versioning](https://semver.org/), and is automated through [Conventional Commits](https://conventionalcommits.org). All pull requests must ensure that the _title_ follows conventional commits.[^versioning-prs]

[^versioning-prs]: We encourage squashing PR's by default. Therefore, you can make the individual commits whatever you want, but the PR title must follow conventional commits. The CI will check this and complain at you until you fix it.
