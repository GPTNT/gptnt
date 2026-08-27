---
title: Prepare GPTNT
---

# Prepare GPTNT

Once you have things installed, we next need to run the services and ensure that the benchmark and
access the game.


## Check the state of the repository

The `doctor` command is there to help you identify any possible problems before you run the
benchmark.

You can use the `--config-only` flag to check the benchmark reference, protected content,
image-token settings, and every discovered player configuration. It does not require Redis, KTANE,
a display, local services, or the full machine checks.

```bash
gptnt doctor --config-only # (1)!
```

1. `--config-only` check the benchmark configuration itself and does not require Redis, KTANE, or
any other services.

??? help "If you get `gptnt: command not found`"

    If the `gptnt` command is not found, you likely need to activate the virtual environment.

    ```bash title="Check the virtual environment"
    which python
    ```

    The output should be a path under `gptnt/.venv/bin/python`.

    === "Automatic activation"

        If you used `mise` to install the benchmark, you can get it to activate it automatically
        when you `cd` into the dir.

        Create a file named `.mise.toml` in the `gptnt/` root with the following contents:

        ```toml title=".mise.toml"
        [env]
        _.python.venv = ".venv"
        ```

        Then, when you `cd` into the `gptnt/` root, `mise` will automatically activate the virtual
        environment for you.

    === "Prefix `uv run`"

        If you run every command with `uv`, it will automatically activate the virtual environment
        for you. For example, to run the above command, you would run:

        ```bash
        uv run gptnt doctor --config-only
        ```

    === "Manual activation"
        If you don't want to use `mise` to manage the virtual environment, there are many other
        ways and we refer you to [uv's documentation](https://docs.astral.sh/uv/pip/environments/#using-a-virtual-environment) for the details.


!!! warning "Not all issues are fatal"
    The `doctor` command reports the issues it finds, but not all of them matter. For example, if
    an old player config is found, it will be a failure but if you are not using that model, then
    it doesn't matter.




See the [`doctor` reference](../reference/cli/doctor.md){data-preview} for every mode and report
section. If this check fails, start with
[installation and doctor troubleshooting](../troubleshooting/installation-and-doctor.md).


## Provide KTANE

!!! danger "You must provide the game"
    GPTNT does not distribute KTANE. Purchase a DRM-free copy from the
    [Humble Bundle store](https://humblebundle.com/store/keep-talking-and-nobody-explodes) and copy
    it under `storage/ktane/`.

GPTNT expects the game executable to be in the `storage/ktane/` directory. Depending on your
platform, the game directory layout is different.

Copy-paste your KTANE game that you downloaded under `storage/ktane`.[^game-path] It is discovered by `src/gptnt/ktane/executable.py` (`get_executable_path`), which raises `GameNotFoundError` if it cannot find one.

[^game-path]: This path is included in the `.gitignore` so it won't get committed.




=== "Linux"

    ```yaml title="Expected Linux layout"
    storage/ktane/
    ├── <name>.x86_64
    └── ktane_Data/
    ```

=== "macOS"

    ```yaml title="Expected macOS layout"
    storage/ktane/
    └── <name>.app/ # (1)!
    ```

    1. If you are using VSCode, it may show the `*.app` bundle as a folder. This is normal and expected so there's nothing to worry about. It's just how `*.app` files work.

=== "Windows"

    ```yaml title="Expected Windows layout"
    storage/ktane/
    ├── <name>.exe
    └── ktane_Data/
    ```

### KTANE Mods

The benchmark is supplied with some pre-built mods so you can run GPTNT without needing to build
the mod yourself.

1. [Gptnt Plays](https://github.com/GPTNT/gptntPlays) is our mod that allows GPTNT to control the
game.
2. [Rule Seed Modifier](https://steamcommunity.com/sharedfiles/filedetails/?id=2037350348) by
[@samfundev](https://github.com/samfundev), [@CaitSith2](https://github.com/CaitSith2), and others,
allows us to control the randomisation of the rules in the manual.

If you would like to use more mods for KTANE, you can provide them in the `storage/ktane/mods/`
directory. The KTANE used for the benchmark is configured to load mods from that directory.


## Run the infrastructure (with Docker Compose)

We use Docker Compose to start Redis and an OpenTelemetry collector. Redis is used as a message bus
for the various services in the benchmark. The OpenTelemetry collector is optional and can be used
to export traces to a local or remote endpoint. The benchmark does not require the collector to be
running but if you would like to review logs and even debug what is happening, we **highly
recommend it.**

We've provided a Docker Compose configuration that starts Redis and the OpenTelemetry collector. You can start it with the following command:

```bash
docker compose up
```

??? question "What if you don't have Docker?"
    If you don't have Docker, you can just run Redis yourself. The default configuration is to listen on `localhost:6379` with no password. Check the `docker-compose.yml` file for the exact configuration to copy from.

??? question "Why no password for Redis?"
    We don't use a password for Redis because it is only accessible from the local machine and there was no one else using the machine and nothing else running on it. Of course, the correct thing to do, especially if you are accessing Redis remotely, is to **set a password and configure the services to use it.**

??? question "What if you don't want to use OpenTelemetry?"
    The most robust option is to set the `COMPOSE_PROFILES` environment variable to `dev` to send all traces to the void. Not using OpenTelemetry will make deubugging harder, so we recommend you keep it enabled unless you know you don't need it.

    ```bash
    COMPOSE_PROFILES=dev docker compose up
    ```

    Observability presets control instrumentation, not log verbosity. See
    [environment configuration](../reference/configuration/environment.md#observability).



??? question "What if I need `sudo` for Docker?"
    If your Docker installation requires `sudo`, prefix the command with `sudo -E` to preserve the environment variables. For example:

    ```bash
    sudo -E docker compose up
    ```


## Rendering the game { #make-sure-the-game-can-render }

The game has to render _somewhere_. If you have a display, like on macOS or Windows, you don't need to do anything. If you are on Linux, you may need to start an X display.

!!! warning "The game must run on a machine that can render graphics"
    KTANE is a Unity game. The machine that runs the game needs a working graphics/display stack: for example, a normal desktop/laptop display, a workstation GPU such as an NVIDIA RTX card, or a headless Linux machine with Xorg backed by a graphics-capable GPU.

    This is separate from the GPU you might use for model inference. Common ML accelerator machines with A100, H100, TPU, or similar compute-focused hardware are often configured for batch/model workloads only and may not be able to back an X display for the game. If your model runs on that kind of machine, run KTANE on a graphics-capable machine and point your player config at the remote model endpoint instead.

    When the game machine and model machine are different, the game-running machine must be able to reach the model server's API. That can be a private network address, a VPN, SSH port forwarding, or a tunnel. In our setups, Cloudflare Tunnel has been a convenient way to expose a self-hosted vLLM endpoint as an HTTPS `base_url`.

We have validated the following cases:

- **macOS/Windows:** nothing to do.
- **Linux with a desktop session:** if `$DISPLAY` is already set, the game uses it—nothing to do.
- **Linux, headless:** start a GPU-backed Xorg with `scripts/startx.py`, then either export
`$DISPLAY` for the run to inherit, or name the display(s) in the run manifest.

??? tip "How to run a headless X display on Linux"
    If you need to use sudo and you still want to use uv/similar, you can use `sudo -E` to preserve the environment variables. For instance, to run an X display on display 3, you can run:

    ```bash
    sudo -E .venv/bin/python scripts/startx.py 3
    ```



## Check everything together

Run the full doctor for everything and make sure it's all working together.

```bash
gptnt doctor
```

!!! tip "Check the mod works too"
  Use the `--check-mod-load` flag to also verify that KTANE can be loaded and that the mod is
  working properly. This is slower and does launch the game, but it's the most complete check.

  ```bash
  gptnt doctor --check-mod-load
  ```
