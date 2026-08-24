# CLI, configuration, and runtime

Use this guide when adding a command, reading configuration or environment variables, constructing
runtime services, logging, or handling timestamps.

## CLI

<!-- rule:gptnt:701 -->

- Define CLI commands with Cyclopts and follow the existing `App` and `Group(sort_key=...)` layout
  in `src/gptnt/cli/__main__.py`. Do not introduce Typer, Click, or argparse for another command
  surface.

<!-- rule:gptnt:702 -->

- Give each command its own module and command function. Define reusable command parameters as
  module-level `Annotated[T, Parameter(...)]` aliases so their parsing and validation remain the
  same at every command that accepts them. `ManifestArgument` in `src/gptnt/cli/doctor/command.py`
  and `SourceOption` in `src/gptnt/cli/experiments/source.py` demonstrate this structure.

<!-- rule:gptnt:703 -->

- Register a command with a lazy import-path string, for example
  `app.command("gptnt.cli.doctor.command:doctor", name="doctor", ...)`. A direct import at CLI
  module load may load optional or expensive dependencies before `--help` can render.

<!-- rule:gptnt:704 -->

- Validate command-line input through `Parameter(validator=...)` raising `ValueError`, or use a
  Cyclopts type such as `ExistingFile` when it already implements the required check. Add a custom
  check only when the framework type cannot express the constraint.

<!-- rule:gptnt:323 -->

- Write model references as `provider:model`, for example `anthropic:claude-opus-4-8`, in code,
  configuration, and CLI input. Player and model names use the publisher identifier expected by the
  provider integration.

<!-- rule:gptnt:705 -->

- Keep commands independently invocable. Do not add a flag whose only purpose is to run another
  command after the first. Users can compose commands in the shell. The `run` command is the
  application orchestrator and may coordinate its documented end-to-end workflow.

<!-- rule:gptnt:713 -->

- Name an optional preview flag that suppresses side effects `--dry-run` and default it to `False`.
  A command that deletes data or changes remote state previews by default and requires `--execute`
  to apply the change. `cleanup-outputs` and `reconcile-wandb` use this convention.

## Configuration and runtime

### Environment and application settings

<!-- rule:gptnt:310 -->

- Declare environment variables controlled by `gptnt` on one `BaseSettings` type with their types,
  defaults, aliases, and validation. Read a third-party variable directly only when the third-party
  library defines its meaning, as with `WANDB_ENTITY`.

<!-- rule:gptnt:706 -->

- Define application filesystem locations on `Paths`, including environment aliases and derived
  directories. Construct `Paths` where a command or service needs its locations. Do not repeat a
  path calculation or environment lookup at individual call sites.

<!-- rule:gptnt:707 -->

- Compose player configuration through `compose_player_config(player, provider)`. Run composition
  sequentially because each call clears Hydra's process-wide singleton; concurrent calls can change
  the singleton while another composition is using it. Core validation and statics use the same
  function in `src/gptnt/common/hydra.py`.

<!-- rule:gptnt:708 -->

- Construct objects described by composed Hydra configuration with
  `hydra.utils.instantiate(...)` so the configured target and arguments determine the runtime type.

<!-- rule:gptnt:711 -->

- Run concurrent work with `anyio.create_task_group()` and `start_soon`. Do not use `asyncio`
  directly; every entrypoint runs under `anyio.run`. Poll with the `periodic()` helper in
  `src/gptnt/common/async_ops.py` when the first check may wait one interval. Keep an explicit
  loop when the first check must run immediately, because `periodic()` sleeps before it yields.

## Logging, time, and observability

<!-- rule:gptnt:709 -->

- Create a module-level logger with `structlog.get_logger()`. Use `logfire.instrument(...)` for
  spans where the surrounding package already records them. Do not add a standard-library logger to
  a module that participates in the structured logging pipeline.

<!-- rule:gptnt:710 -->

- Use `whenever.Instant` for application timestamps. Convert an external `datetime` at the boundary
  instead of allowing both timestamp types to propagate through the application.

<!-- rule:gptnt:712 -->

- Write a structlog event name as a fixed string and bind values as keyword fields. Do not
  interpolate a value into the event name; the value becomes part of the event key, and the
  structured pipeline cannot group on it. Use `logger.exception` inside an exception handler and
  `logger.error` outside one.
