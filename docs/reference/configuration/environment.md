---
title: Environment configuration
tags:
  - Configuration
  - Runtime
---

# Environment configuration

GPTNT reads paths, runtime endpoints, game settings, instrumentation flags, and service timeouts
from environment variables. This page groups each value by the object or command that owns it.

## Paths and command inputs

| Variable | Default | Owner and effect |
| -------- | ------- | ---------------- |
| `CONFIGS` | `configs/` in a checkout, then packaged `gptnt/_configs` | Overrides the complete configuration root. |
| `EXPERIMENT_SPECS_DIR` | `output/experiment_specs/` | Default specification root for `generate` and `submit`. `generate` appends the manifest stem when no explicit output is supplied. |
| `EXPERIMENT_RECORDER_OUTPUTS` | Unset | Pins one run recorder directory. Unset runs create a timestamp under `output/experiment_recorder_outputs/`. |
| `EXPERIMENT_RECORDER` | Command-specific | Supplies a local player-record or completion directory to `submit`, `status`, and `build-db`. |
| `EXPERIMENTS_DB` | `output/experiments.duckdb` | Supplies the DuckDB path to database and submission commands. |
| `STATICS_OUTPUTS` | `output/` | Supplies the root containing `<task>_predictions/<model>/` to submission commands. |
| `SUBMISSIONS_DIR` | `output/submissions/` | Supplies the destination for built submission bundles. |
| `SUBMITTER` | Unset | Supplies the submission identity aggregate where the command accepts it. |

`EXPERIMENT_RECORDER_OUTPUTS` selects the directory written by child recorder processes.
`EXPERIMENT_RECORDER` selects an existing directory read by a command. They are different
boundaries.

## Runtime endpoints

| Variable | Type and default | Effect |
| -------- | ---------------- | ------ |
| `GPTNT_EM_HOST` | String, `localhost` | Experiment-manager host used by health, submission, and status clients. |
| `GPTNT_EM_PORT` | Integer, `8085` | Experiment-manager HTTP port. |
| `REDIS_DSN` | Redis DSN, `redis://localhost:6379` | Redis endpoint used by the experiment manager, game services, player services, heartbeats, and RPC. |

`GPTNT_MANUAL_ARTIFACTS` is not user-authored configuration. `gptnt run` serialises prepared manual
paths into it for player child processes.

## Display

On Linux, `DISPLAY` identifies the X display inherited by a game process. A manifest `displays`
list overrides it per room by assigning `:<number>` round-robin. Omitting `displays` leaves the
ambient value unchanged.

=== "Linux"

    A local display commonly uses a value such as `DISPLAY=:0`. Doctor also checks the matching
    `/tmp/.X11-unix/X0` socket. A missing socket produces a warning because remote TCP displays can
    still be valid.

=== "macOS"

    GPTNT does not require an X display. KTANE uses the desktop application environment.

=== "Windows"

    GPTNT does not require an X display. KTANE uses the desktop application environment.

## KTANE settings

`KtaneSettings` uses the `KTANE_` prefix.

| Variable | Default | Effect |
| -------- | ------- | ------ |
| `KTANE_PLAYER_SETTINGS_FILE_NAME` | `playerSettings.xml` | Saved player-settings filename. |
| `KTANE_PROGRESSION_FILE_NAME` | `progression.xml` | Saved progression filename. |
| `KTANE_WINDOWS` | `%APPDATA%/../LocalLow/Steel Crate Games/Keep Talking and Nobody Explodes` | Windows settings directory. |
| `KTANE_MAC` | `~/Library/Application Support/com.steelcrategames.keeptalkingandnobodyexplodes` | macOS settings directory. |
| `KTANE_LINUX` | `~/.config/unity3d/Steel Crate Games/Keep Talking and Nobody Explodes` | Linux settings directory. |
| `KTANE_GAME_WIDTH` | `640` | Game-render width in pixels. |
| `KTANE_GAME_HEIGHT` | `480` | Game-render height in pixels. |
| `KTANE_GAME_SPEED` | `1` | Game-speed multiplier. |
| `KTANE_MUSIC_VOLUME` | `0` | Music volume from 0 to 100. |
| `KTANE_SFX_VOLUME` | `0` | Sound-effect volume from 0 to 100. |
| `KTANE_LANGUAGE_CODE` | `en` | One of the language codes supported by KTANE. |

GPTNT sets child-process `GAME_WIDTH` and `GAME_HEIGHT` from the configured dimensions. Configure
the `KTANE_` values rather than setting those child variables directly.

## Observability

`ObservabilitySettings` uses the `OBSERVABILITY_` prefix except for the standard OTLP endpoint.

| Variable | Default | Effect |
| -------- | ------- | ------ |
| `OBSERVABILITY_ENABLE_METRICS` | `true` | Enables runtime metrics. |
| `OBSERVABILITY_INSTRUMENT_FASTAPI` | `true` | Instruments FastAPI. |
| `OBSERVABILITY_INSTRUMENT_FASTSTREAM` | `true` | Instruments FastStream. |
| `OBSERVABILITY_INSTRUMENT_HTTPX` | `true` | Instruments HTTPX requests. |
| `OBSERVABILITY_INSTRUMENT_PYDANTIC_AI` | `true` | Instruments Pydantic AI model calls. |
| `OBSERVABILITY_INSTRUMENT_REDIS` | `false` | Instruments Redis operations. |
| `OBSERVABILITY_CAPTURE_SPAN_TIMINGS` | `false` | Writes per-step timing JSONL beside experiment records. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318/` | OTLP collector endpoint. |
| `OTEL_RESOURCE_ATTRIBUTES` | Existing environment value | Adds resource attributes. The `limited` run preset adds `sampling.aggressive=true`. |

The run-manifest presets have these effects:

| Preset | Instrumentation |
| ------ | --------------- |
| `full` | Leaves the environment unchanged, so the settings defaults apply. |
| `limited` | Keeps Pydantic AI instrumentation and requests aggressive tail sampling. Disables other listed instrumentation and metrics. |
| `off` | Disables metrics and every listed instrumentation flag. |

!!! note "Instrumentation is not log verbosity"
    These settings control metrics and tracing hooks. Child process logs are still written by the
    run orchestrator.

## Service timeouts

`ServiceTimeouts` has no environment prefix. Pydantic Settings accepts the uppercase field name.
All values are seconds.

| Variable | Default | Operation |
| -------- | ------- | --------- |
| `HEARTBEAT_REPEAT_INTERVAL` | `3` | Send heartbeat hashes. |
| `HEARTBEAT_CHECK_INTERVAL` | `2` | Scan Redis for heartbeats. |
| `HEARTBEAT_EXPIRATION` | `10` | Expire a heartbeat and its service. |
| `TOMBSTONE_EXPIRATION` | `120` | Retain graceful-shutdown diagnostics. |
| `GAME_STATE_INTERVAL` | `2` | Poll game state. |
| `GET_BOMB_STATE_TIMEOUT` | `10` | Wait for bomb state. |
| `GET_OBSERVATION_TIMEOUT` | `60` | Wait for game frames and observations. |
| `UPDATE_METRICS_INTERVAL` | `5` | Refresh runtime metrics. |
| `CONFIGURE_SERVICES_TIMEOUT` | `60` | Configure a matched game and players. |
| `RUN_FORWARD_PASS_TIMEOUT` | `600` | Wait for one player model pass. |
| `REDIS_RPC_TIMEOUT` | `600` | Default Redis request/response timeout. |
| `MAXIMUM_EXPERIMENT_DURATION` | `12000` | Stop an experiment that exceeds the runtime limit. |
| `SESSION_STATE_WATCHER_INTERVAL` | `1` | Check session service states. |
| `GAME_REQUEST_TIMEOUT` | `5` | Wait for a short game-control request. |

Changing a timeout changes failure detection and can alter resource retention. Use the default
unless the deployment has a measured need for another value.

## External integrations

GPTNT passes provider, W&B, OpenTelemetry, and submission variables to the external library that
owns them. Common local boundaries include:

- `WANDB_ENTITY`, `WANDB_PROJECT`, and `WANDB_MODE` for W&B completion and recording.
- Provider credentials such as `ANTHROPIC_API_KEY`, `AZURE_OPENAI_API_KEY`,
  `ANTHROPIC_FOUNDRY_API_KEY`, and `VLLM_API_KEY`.
- `LOGFIRE_TOKEN` for the production collector deployment.
- `GITHUB_TOKEN` for remote submission operations.

Use the provider's documentation for its complete variable set. The [provider configuration](providers.md)
and [provider troubleshooting](../../troubleshooting/providers-and-model-responses.md) pages cover
the GPTNT boundary. Do not place credentials in a tracked run, player, or provider configuration.

[Install and check GPTNT](../../get-started.md){ .md-button }
[Troubleshoot Redis and services](../../troubleshooting/redis-and-runtime-services.md){ .md-button }
