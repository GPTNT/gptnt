---
title: Game and display troubleshooting
tags:
  - Runtime
---

# Game and display troubleshooting

Separate file layout, mod loading, saved settings, display access, and leftover process state. The
full doctor report checks each condition independently.

## The game binary is missing or ambiguous

Place exactly one supported executable under `storage/ktane/`.

=== "Linux"

    Provide one `*.x86_64` executable and its `ktane_Data/` directory.

=== "macOS"

    Provide one `*.app` bundle. An editor can display the bundle as a directory.

=== "Windows"

    Provide one `*.exe` executable and its `ktane_Data/` directory.

Run the full doctor check again:

```bash title="Check the game and display"
gptnt doctor runs/<name>.yaml
```

## The GPTNT mod is missing

Install the mod at:

```text title="Expected mod directory"
storage/ktane/mods/Gptnt Plays/
```

The file check only proves the directory exists. Confirm that the game loads the mod with:

```bash title="Check the KTANE mod"
gptnt doctor runs/<name>.yaml --check-mod-load
```

The probe starts bare KTANE and polls the mod `/health` endpoint for up to 45 seconds. It skips when
the binary, mod directory, or Linux display prerequisite has already failed.

## Linux has no display

!!! failure "`$DISPLAY` is not set"
    Use an existing desktop display or start a GPU-backed Xorg display. A compute accelerator alone
    does not provide the Unity rendering stack.

```bash title="Start a virtual display"
sudo -E .venv/bin/python scripts/startx.py 3
export DISPLAY=:3
```

Repeat doctor in the same shell so it inherits `DISPLAY`.

## The X socket is missing

Doctor maps `DISPLAY=:3` to `/tmp/.X11-unix/X3`. A missing local socket produces a warning rather
than a definite failure because a remote or TCP display can still work.

Check that the selected display server is running and accessible to the account that starts GPTNT.
When the manifest contains `displays`, each room receives `:<number>` round-robin instead of the
ambient value.

## The game starts but the mod does not respond

Use `--check-mod-load` and inspect the game process log. The condition can come from a mod that is
not loaded or a game startup failure. The wrong game build and a display that cannot render the
process can cause the same symptom. Redis does not gate this probe.

The game service reference explains failures after the mod responds and the runtime has started.

## Saved settings changed

!!! danger "GPTNT writes automation settings"
    GPTNT writes `playerSettings.xml` and `progression.xml` in the platform KTANE settings
    directory. When an existing file differs from the required content, GPTNT copies it to a
    timestamped `.bak` file before writing the automation version.

Platform defaults are:

=== "Linux"

    `~/.config/unity3d/Steel Crate Games/Keep Talking and Nobody Explodes`

=== "macOS"

    `~/Library/Application Support/com.steelcrategames.keeptalkingandnobodyexplodes`

=== "Windows"

    `%APPDATA%/../LocalLow/Steel Crate Games/Keep Talking and Nobody Explodes`

Use `KTANE_LINUX`, `KTANE_MAC`, or `KTANE_WINDOWS` to override the applicable directory. Keep the
backup until you have confirmed the benchmark and your normal game setup.

## A KTANE process remains after a run

Normal run shutdown terminates the process cluster. Inspect running processes and the log named by
the failed run. If a matching process remains after shutdown, `gptnt kill` provides forced cleanup
for GPTNT interactive entry points and KTANE processes.

!!! danger "Forced cleanup matches processes by command and name"
    Confirm that another user or run does not own a matching process before running `gptnt kill`.

[Game service reference](../reference/runtime/game-service.md)
[Install and check GPTNT](../start-here/install-and-check.md)
