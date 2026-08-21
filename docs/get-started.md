# Get started

## Choose an installation

Use the latest release for a normal benchmark run. A pinned release is for reproducing a result or
investigating a submission. Clone the repository only when you intend to contribute to GPTNT.

| Path | Use it for |
| ---- | ---------- |
| Latest release | Normal benchmark use |
| Pinned release | Reproduction and submission investigation |
| Git clone | Contribution and development |

### Download the latest release

```bash
curl -fsSL \
  https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz |
  tar -xzf -

cd gptnt
mise install
mise run sync
```

The archive contains the source, benchmark data, and the Git metadata used to identify its release.
You do not need a system Git executable to run the bundled benchmark. Do not remove the bundled
`.git` directory: GPTNT reads the release tag and protected-content baseline from it.

`mise run sync` installs the project dependencies and Playwright-managed Chromium. See
[Manuals](manuals.md){data-preview} for manual profiles, caching, offline preparation, and repair.

#### Verify the checksum

Download the archive and its checksum before extracting when you need to verify the bytes:

```bash
curl -fsSLO https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz
curl -fsSLO https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.tar.gz.sha256
sha256sum --check gptnt.tar.gz.sha256
tar -xzf gptnt.tar.gz

cd gptnt
mise install
mise run sync
```

On macOS, use `shasum --algorithm 256 --check gptnt.tar.gz.sha256` when `sha256sum` is not
installed.

#### Use the ZIP archive

```bash
curl -fsSLO https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.zip
curl -fsSLO https://github.com/GPTNT/gptnt/releases/latest/download/gptnt.zip.sha256
sha256sum --check gptnt.zip.sha256
unzip gptnt.zip

cd gptnt
mise install
mise run sync
```

The ZIP contains the same checkout and bundled Git metadata as the tar archive. The macOS checksum
command above also works with `gptnt.zip.sha256`.

### Download a pinned release

Replace `vX.Y.Z` with the release recorded by the result or submission you are investigating:

```bash
curl -fsSLO https://github.com/GPTNT/gptnt/releases/download/vX.Y.Z/gptnt.tar.gz
curl -fsSLO https://github.com/GPTNT/gptnt/releases/download/vX.Y.Z/gptnt.tar.gz.sha256
sha256sum --check gptnt.tar.gz.sha256
tar -xzf gptnt.tar.gz

cd gptnt
mise install
mise run sync
```

The version comes from the release tag in the URL. Latest-download instructions do not carry a
copied version string.

### Clone for contribution and development

```bash
git clone https://github.com/GPTNT/gptnt.git
cd gptnt
mise install
mise run sync
```

This path follows the repository branch instead of a published benchmark release. Read
[Contributing to GPTNT](https://github.com/GPTNT/gptnt/blob/main/CONTRIBUTING.md) before changing the
benchmark.

## Check configuration without infrastructure

```bash
gptnt doctor --config-only
```

This checks the release identity, protected benchmark content, and player configuration without
requiring KTANE, Redis, a display, or the local services. Pass a run manifest as well when you want
to check its roster, for example `gptnt doctor runs/quickstart.yaml --config-only`.

## Provide the game

!!! danger "You must provide the game yourself"
    We do not distribute KTANE. Purchase a DRM-free copy from the
    [Humble Bundle store](https://humblebundle.com/store/keep-talking-and-nobody-explodes) and copy
    it under `storage/ktane`.

GPTNT expects this layout:

| OS | Layout under `storage/ktane` |
| -- | ---------------------------- |
| Linux | `*.x86_64` plus a `ktane_Data/` directory |
| macOS | `*.app` |
| Windows | `*.exe` |

The directory is ignored by Git. VS Code may show a macOS `*.app` bundle as a directory; that is
normal for an application bundle.

## Start the infrastructure

```bash
docker compose up -d
```

Docker Compose starts Redis, which carries messages between the services and players, and the
OpenTelemetry collector. KTANE itself does not run in Docker.

??? question "What if you do not have Docker?"
    Run Redis yourself on `localhost:6379` with no password, or update the service configuration to
    match your Redis instance. `docker-compose.yml` contains the default setup.

??? question "What if you do not want to export traces?"
    Set `COMPOSE_PROFILES=dev` before starting the services. The development profile keeps the
    collector available but discards its output. Without traces, diagnosing a failed run is harder.

## Make sure the game can render

KTANE must run on a machine with a working graphics and display stack. A desktop on macOS or
Windows needs no extra setup. A Linux desktop can use its existing `$DISPLAY`.

!!! warning "Compute accelerators do not imply a game display"
    A headless machine configured for A100, H100, TPU, or similar model workloads may not provide a
    display that can render the Unity game. Run KTANE on a graphics-capable machine and point the
    player configuration at the remote model endpoint when those machines differ.

On headless Linux, start a GPU-backed Xorg display with `scripts/startx.py`, then export `$DISPLAY`
or list displays in the [run manifest](running/run-your-model.md#displays){data-preview}:

```bash
sudo -E .venv/bin/python scripts/startx.py 3
export DISPLAY=:3
```

The game-running machine must be able to reach a remote model server. Use a private network, VPN,
SSH port forwarding, or an HTTPS tunnel that fits your setup.

## Run the quickstart

The quickstart uses dummy players. They do not solve the game, but they exercise configuration,
generation, the local services, KTANE, and result recording.

```bash
gptnt doctor runs/quickstart.yaml
gptnt generate runs/quickstart.yaml
gptnt run runs/quickstart.yaml
```

`doctor` checks the full machine and run plan. `generate` writes the experiment specs. `run` reads
those specs, prepares their manuals, starts the processes, and records the results. With a display,
you will see the game window; on a headless machine, follow the process logs.

## Prior artifacts

!!! warning "Use the matching release and tooling"
    Current tools do not load or convert submission schema version 1 bundles or prior Parquet and
    DuckDB layouts, and they do not upgrade prior databases in place. Inspect an artifact with its
    matching prior release and dependencies. To produce benchmark results under a current release,
    rerun the benchmark. Player fingerprints from earlier formats are not comparable identifiers
    because the fingerprint inputs changed at the version boundary.
