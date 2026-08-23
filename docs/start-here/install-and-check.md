---
title: Install and check GPTNT
tags:
  - CLI
  - Configuration
---

# Install and check GPTNT

Install a GPTNT release, provide the game, start Redis, and verify the machine before running an
experiment. Complete this page from the repository root unless a step says otherwise.

## Choose an installation

Use the latest release for a normal benchmark run. Use a pinned release to reproduce a result or
investigate a submission. Clone the repository only when you intend to contribute to GPTNT.

| Installation | Use it for |
| ------------ | ---------- |
| Latest release | Normal benchmark use |
| Pinned release | Reproduction and submission investigation |
| Repository checkout | Contribution and development |

### Download the latest release

```bash title="Download and install GPTNT"
curl -fsSL \
  https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz |
  tar -xzf -

cd gptnt
mise install
mise run sync
```

The archive contains the source, benchmark inputs, and Git metadata used to identify the release.
You do not need a system Git executable to run the bundled benchmark. Do not remove the bundled
`.git` directory. GPTNT reads the release tag and protected-content baseline from it.

`mise run sync` installs all dependency groups and extras, then installs Playwright-managed
Chromium for manual preparation.

??? question "Is `mise` required?"
    The documented release setup uses `mise` to install the required Python and `uv` versions and
    to run the repository tasks. A direct `uv` sequence is not documented yet because it must also
    reproduce the Playwright installation performed by `mise run sync`.

#### Verify the archive checksum

Download the archive and checksum before extraction when you need to verify the downloaded bytes.

=== "Linux"

    ```bash title="Download and verify the release"
    curl -fsSLO https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz
    curl -fsSLO https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz.sha256
    sha256sum --check gptnt.tar.gz.sha256
    tar -xzf gptnt.tar.gz
    ```

=== "macOS"

    ```bash title="Download and verify the release"
    curl -fsSLO https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz
    curl -fsSLO https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz.sha256
    shasum --algorithm 256 --check gptnt.tar.gz.sha256
    tar -xzf gptnt.tar.gz
    ```

The archive extracts into `gptnt/`. Run `mise install` and `mise run sync` from that directory.

??? note "Use the ZIP archive"
    The release also publishes `gptnt.zip` and `gptnt.zip.sha256`. Download both, verify the
    checksum with the platform command above, and run `unzip gptnt.zip`. The ZIP contains the same
    checkout and bundled Git metadata as the tar archive.

### Download a pinned release

Replace `vX.Y.Z` with the release recorded by the result or submission you are investigating.

```bash title="Download and install a release"
curl -fsSLO https://github.com/GPTNT/gptnt/releases/download/vX.Y.Z/gptnt.tar.gz
curl -fsSLO https://github.com/GPTNT/gptnt/releases/download/vX.Y.Z/gptnt.tar.gz.sha256
sha256sum --check gptnt.tar.gz.sha256
tar -xzf gptnt.tar.gz

cd gptnt
mise install
mise run sync
```

The version comes from the release tag in the URL. The `latest/download` URL does not carry a
copied version string.

### Clone for contribution and development

```bash title="Install from a Git checkout"
git clone https://github.com/GPTNT/gptnt.git
cd gptnt
mise install
mise run sync
```

A repository checkout follows its selected branch rather than a published benchmark release. Read
[Contributing to GPTNT](https://github.com/GPTNT/gptnt/blob/main/CONTRIBUTING.md) before changing
benchmark code or inputs.

## Check configuration without services

```bash title="Check the installation"
gptnt doctor --config-only
```

This checks the benchmark reference, protected content, image-token settings, and every discovered
player configuration. It does not require Redis, KTANE, a display, local services, or the full
machine checks.

Pass the included manifest to check only its player roster and add its run-plan checks:

```bash title="Validate the quickstart configuration"
gptnt doctor runs/quickstart.yaml --config-only
```

!!! success "Configuration is ready"
    A successful doctor command exits without a failing row. The report has no separate final
    success sentence.

See the [`doctor` reference](../reference/cli/doctor.md){data-preview} for every mode and report
section. If this check fails, start with
[installation and doctor troubleshooting](../troubleshooting/installation-and-doctor.md).

## Provide KTANE

!!! danger "You must provide the game"
    GPTNT does not distribute KTANE. Purchase a DRM-free copy from the
    [Humble Bundle store](https://humblebundle.com/store/keep-talking-and-nobody-explodes) and copy
    it under `storage/ktane/`.

GPTNT expects one game executable in the platform layout:

=== "Linux"

    ```text title="Expected Linux layout"
    storage/ktane/
    ├── <name>.x86_64
    └── ktane_Data/
    ```

=== "macOS"

    ```text title="Expected macOS layout"
    storage/ktane/
    └── <name>.app/
    ```

=== "Windows"

    ```text title="Expected Windows layout"
    storage/ktane/
    ├── <name>.exe
    └── ktane_Data/
    ```

Install the GPTNT mod at `storage/ktane/mods/Gptnt Plays/`. The game directory is ignored by Git.
A macOS `*.app` is an application bundle, so an editor may display it as a directory.

## Start Redis and telemetry

```bash title="Start Redis"
docker compose up -d
```

Docker Compose starts Redis and an OpenTelemetry collector. Redis carries service heartbeats, RPC
requests, and player messages. KTANE does not run in Docker.

!!! warning "Do not expose the default Redis service"
    The Compose configuration runs Redis on `localhost:6379` without authentication. Do not expose
    that endpoint to an untrusted network. Set `REDIS_DSN` when GPTNT must use a differently
    configured Redis service.

??? question "What if Docker is unavailable?"
    Run Redis yourself on `localhost:6379` without a password, or set `REDIS_DSN` to the endpoint
    and credentials for your Redis service. The OpenTelemetry collector is optional.

??? question "What if traces must stay local?"
    Start the development Compose profile. It keeps the collector endpoint available but discards
    the exported telemetry.

    ```bash title="Start Redis and telemetry"
    COMPOSE_PROFILES=dev docker compose up -d
    ```

    Observability presets control instrumentation, not log verbosity. See
    [environment configuration](../reference/configuration/environment.md#observability).

## Provide a game display { #make-sure-the-game-can-render }

KTANE must run on a machine with a working graphics and display stack. A desktop on macOS or
Windows doesn't need an extra X display. A Linux desktop can use its existing `$DISPLAY`.

!!! warning "A compute accelerator does not provide a game display"
    A headless machine configured for model workloads may not provide a display that can render
    the Unity game. Run KTANE on a graphics-capable machine. A player can connect to a model
    endpoint on another machine when the network permits it.

On headless Linux, start a GPU-backed Xorg display and export it:

```bash title="Start a virtual display"
sudo -E .venv/bin/python scripts/startx.py 3
export DISPLAY=:3
```

The display number `3` creates `$DISPLAY=:3`. A run manifest can also list display numbers and
assign rooms to them. See [game and display troubleshooting](../troubleshooting/game-and-displays.md)
when the X socket or game window is unavailable.

## Check the complete machine

Run the full doctor report against the included manifest:

```bash title="Validate the quickstart environment"
gptnt doctor runs/quickstart.yaml
```

The report checks the run plan, Redis, game files, mod files, Linux display, experiment-manager
port, optional telemetry endpoint, machine capacity, and configured players. Add the slower game
probe when you need to confirm that the mod serves its health endpoint:

```bash title="Check the KTANE mod"
gptnt doctor runs/quickstart.yaml --check-mod-load
```

The probe starts the bare game, waits up to 45 seconds for its `/health` endpoint, and then stops
the game. Redis is not required for this probe.

!!! success "The machine is ready"
    The full command exits without a failing row. A warning can describe an optional service or a
    condition that needs interpretation. Read the row before continuing.

## Keep older artefacts with their release { #prior-artifacts }

!!! warning "Use matching release tools"
    Current tools do not convert submission schema version 1 bundles or earlier Parquet and DuckDB
    layouts. They do not upgrade prior databases in place. Inspect an artefact with its matching
    release and dependencies. Rerun the benchmark to produce current results. Player fingerprints
    from different format boundaries are not comparable identifiers.

<!-- vale ai-tells.DoubleHyphen = NO -->
[Run the quickstart](run-quickstart.md)
[Doctor reference](../reference/cli/doctor.md)
<!-- vale ai-tells.DoubleHyphen = YES -->
