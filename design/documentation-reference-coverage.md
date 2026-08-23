# Documentation reference coverage inventory

- Status: checked Stage 1 planning evidence
- Applies to: GPTNT v2 and later
- Evidence base: `origin/v2` implementation, configuration, templates, tests, and rendered CLI help
- Public site status: not published

## Purpose

This inventory records the v2 interfaces that the documentation reference must cover. It assigns
each interface to a proposed reference page, selects a hand-written or generated presentation, and
records the procedure and concept pages that should link to it. It is planning evidence for the
documentation programme, not public documentation or a replacement for generated schemas.

The inventory separates supported Python integration points from contributor-only implementation
types. A model may appear in generated configuration or file-schema reference without creating a
supported Python import. A public module does not make every object in that module a supported
interface.

## Method and notation

The inventory was checked against:

- Cyclopts registrations, command functions, reusable parameters, and rendered help.
- Pydantic models, dataclasses, settings classes, Hydra configuration, and templates.
- Serialisers, readers, compatibility checks, database schema generation, and output paths.
- Package exports and the call sites that construct or consume candidate Python interfaces.
- Runtime entry points, service clients, command handlers, heartbeats, registries, and recorders.

Presentation modes are:

- **H+V**: hand-written scope and relationships with option or format detail verified from source.
- **H+G**: hand-written scope and relationships followed by generated local model or API output.
- **H+E**: hand-written GPTNT-specific behavior with links to the external API documentation.

Cross-link labels are:

| Label | Planned page                                      |
| ----- | ------------------------------------------------- |
| P1    | Install and check GPTNT                           |
| P2    | Run the quickstart                                |
| P3    | Add a model and configure a provider              |
| P4    | Prepare manuals                                   |
| P5    | Create a run manifest and generate specifications |
| P6    | Run and resume interactive experiments            |
| P7    | Inspect and analyse results                       |
| P8    | Run static evaluations                            |
| P9    | Submit results                                    |
| C1    | Benchmark and player model                        |
| C2    | Experiment hierarchy                              |
| C3    | Roles, protocols, and capabilities                |
| C4    | Suites, revisions, and comparability              |
| C5    | Runtime services                                  |
| C6    | Results and provenance                            |
| C7    | Manuals and rule seeds                            |

## CLI coverage

`src/gptnt/cli/__main__.py` registers 20 top-level commands. Six of those commands are groups. The
groups contain 21 nested leaf commands.

### System and onboarding

| Interface and verified parameters                                                                | Evidence                                                                           | Proposed owner                             | Mode | Cross-links |
| ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- | ------------------------------------------ | ---- | ----------- |
| `doctor [MANIFEST]`; `--check-mod-load`, `--live`, `--config-only`, `--allow-modified-benchmark` | `src/gptnt/cli/doctor/command.py`                                                  | `reference/cli/doctor.md`                  | H+V  | P1, P5, C5  |
| `new player NAME`; name accepts letters, digits, `_`, and `-`                                    | `src/gptnt/cli/player/new.py`                                                      | `reference/cli/model-configuration.md`     | H+V  | P3          |
| `new provider NAME`; same name constraint                                                        | `src/gptnt/cli/player/new.py`                                                      | `reference/cli/model-configuration.md`     | H+V  | P3          |
| `measure-tokens-per-image PLAYER CALIBRATION-IMAGE`; optional `--provider`                       | `src/gptnt/cli/onboarding/measure_tokens_per_image.py`, `src/gptnt/cli/_params.py` | `reference/cli/model-configuration.md`     | H+V  | P3, C3      |
| `list suites`; no parameters                                                                     | `src/gptnt/cli/onboarding/list_configs.py`                                         | `reference/cli/configuration-discovery.md` | H+V  | P5, C4      |
| `list players`; no parameters; output also lists providers                                       | `src/gptnt/cli/onboarding/list_configs.py`                                         | `reference/cli/configuration-discovery.md` | H+V  | P3          |

### Generation and manuals

| Interface and verified parameters                                                                                   | Evidence                                                                 | Proposed owner                         | Mode | Cross-links           |
| ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------- | ---- | --------------------- |
| `generate MANIFEST`; `--output-dir`, `--allow-modified-benchmark`; `--output-dir` also reads `EXPERIMENT_SPECS_DIR` | `src/gptnt/cli/onboarding/generate_specs.py`                             | `reference/cli/generate.md`            | H+V  | P2, P5, C2            |
| `generate-missions NAME`; no options                                                                                | `src/gptnt/cli/onboarding/generate_missions.py`                          | `reference/cli/missions-and-suites.md` | H+V  | P5, C4, C7            |
| `suite freeze`; `--check`, `--allow-modified-benchmark`                                                             | `src/gptnt/cli/suite/__main__.py`                                        | `reference/cli/missions-and-suites.md` | H+V  | C4, suite-lock format |
| `manual download`; repeatable `--suite`, or `--all-profiles`                                                        | `src/gptnt/cli/manual/download.py`, `src/gptnt/cli/manual/_selection.py` | `reference/cli/manuals.md`             | H+V  | P4, C7                |
| `manual compile`; repeatable `--suite`, or `--all-profiles`                                                         | `src/gptnt/cli/manual/compile.py`, `src/gptnt/cli/manual/_selection.py`  | `reference/cli/manuals.md`             | H+V  | P4, C7                |

`--suite` and `--all-profiles` are mutually exclusive. Omitting both selects profiles required by
the configured suites.

### Interactive execution

| Interface and verified parameters                                                                               | Evidence                                                                     | Proposed owner                             | Mode | Cross-links                 |
| --------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------ | ---- | --------------------------- |
| `run MANIFEST`; `--force`, `--allow-modified-benchmark`, `--interactive` or `-i`                                | `src/gptnt/cli/run/command.py`                                               | `reference/cli/run.md`                     | H+V  | P2, P6, C5                  |
| `submit`; `--experiment-specs-dir`, `--source`, `--output-dir`, `--dry-run`, `--no-filter`, `--delete-unneeded` | `src/gptnt/cli/interactive/submit.py`, `src/gptnt/cli/experiments/models.py` | `reference/cli/run.md`                     | H+V  | P6, completion ledger       |
| `kill`; no parameters                                                                                           | `src/gptnt/cli/interactive/kill.py`                                          | `reference/cli/run.md`                     | H+V  | P6, runtime troubleshooting |
| `status [SOURCES ...]`; `--source`, `--output-dir`                                                              | `src/gptnt/cli/experiments/status.py`                                        | `reference/cli/results-and-maintenance.md` | H+V  | P6, P7, C6                  |

`submit` and `status` accept completion sources `local` and `wandb`. Their local completion output
directory reads `EXPERIMENT_RECORDER`. `submit --experiment-specs-dir` reads
`EXPERIMENT_SPECS_DIR`. `status` does not require a source token. It also accepts one directory or
one or more suite IDs.

### Results, analysis, and maintenance

| Interface and verified parameters                                                                                          | Evidence                                     | Proposed owner                             | Mode | Cross-links             |
| -------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------ | ---- | ----------------------- |
| `cleanup-outputs`; `--target`, `--execute`; previews without `--execute`                                                   | `src/gptnt/cli/experiments/cleanup.py`       | `reference/cli/results-and-maintenance.md` | H+V  | P7, interrupted outputs |
| `reconcile-wandb`; `--directory`, `--execute`, `--include-dummy-runs`, `--mark-missing-output-as-old` or its negative form | `src/gptnt/cli/experiments/cleanup_wandb.py` | `reference/cli/results-and-maintenance.md` | H+V  | P7, C6                  |
| `build-db DIRECTORY`; `--output` or `-o`, `--max-workers` or `-j`, `--skip-filtering`, `--delete-existing-db`              | `src/gptnt/cli/experiments/build_db.py`      | `reference/cli/results-and-maintenance.md` | H+V  | P2, P7, DuckDB          |
| `analyse`; no parameters                                                                                                   | `src/gptnt/cli/analysis/launch.py`           | `reference/cli/results-and-maintenance.md` | H+V  | P7                      |
| `timing RUN-DIR`; no options                                                                                               | `src/gptnt/cli/experiments/timing.py`        | `reference/cli/results-and-maintenance.md` | H+V  | P7, C5                  |
| `results`; optional `--db-path`                                                                                            | `src/gptnt/cli/experiments/results.py`       | `reference/cli/results-and-maintenance.md` | H+V  | P2, P7, C6              |

`build-db DIRECTORY` reads `EXPERIMENT_RECORDER`. Its output reads `EXPERIMENTS_DB`. The default
database for `results` is `output/experiments.duckdb`.

### Static evaluations

The owner for all static commands is `reference/cli/statics.md`. Each command uses H+V and links to
P8, C3, C6, and the static-output formats.

These ten commands share required `--player` and optional `--provider`, `--download`, `--throw`,
`--upload`, `--limit-instances`, `--dataset-revision`, `--allow-thinking` or `--no-thinking`, and
`--allow-modified-benchmark`:

- `statics defuser-grounding-coordinates`
- `statics defuser-grounding-som`
- `statics defuser-vqa-oe`
- `statics defuser-vqa-mcq`
- `statics defuser-state-recognition-vqa-mcq`
- `statics expert-vqa`
- `statics expert-vqa-no-manual`
- `statics expert-ocr`
- `statics expert-ocr-with-text`
- `statics expert-element-grounding`

The shared evidence is `src/gptnt/cli/statics/_params.py` and `src/gptnt/cli/_params.py`. Each leaf
command is defined in the matching module under `src/gptnt/cli/statics/`.

`defuser-state-recognition-vqa-mcq` also accepts `--state-split`. The command validates
`state-change`, `solved`, and `strikes`. `expert-ocr-with-text` also requires
`--manual-artifact`.

`statics how-do-you` is separate. It accepts required `--player`, optional `--provider`, positive
`--attempts`, `--allow-thinking` or `--no-thinking`, and `--output-file-prefix`. It does not accept
the shared dataset, download, execution, upload, or benchmark-integrity options. Its evidence is
`src/gptnt/cli/statics/how_do_you.py`.

### Submission

The owner for this group is `reference/cli/submission.md`. Each command uses H+V and links to P9,
C4, C6, and the submission-bundle formats.

| Interface and verified parameters                                                                                                                                                                                     | Evidence                                                                                |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `submission new`; `--experiments-db`, `--statics-output-dir`, `--output-dir`, repeatable `--suite`, repeatable `--static`, repeatable `--model`, `--submitter.name`, `--submitter.contact`, `--submitter.affiliation` | `src/gptnt/cli/submission/new.py`, `src/gptnt/cli/submission/_schema.py`, rendered help |
| `submission validate`; `--path`, `--format` with `rich`, `json`, or `github`                                                                                                                                          | `src/gptnt/cli/submission/validate.py`                                                  |
| `submission submit`; `--path`, `--repo`, `--dry-run`                                                                                                                                                                  | `src/gptnt/cli/submission/submit.py`                                                    |

The three `submission new` directories read `EXPERIMENTS_DB`, `STATICS_OUTPUTS`, and
`SUBMISSIONS_DIR`. The source parameter for the submitter aggregate declares `SUBMITTER`; rendered
help expands the model into the three nested submitter options.

## Configuration coverage

### User-editable local schemas

| Configuration           | Objects and evidence                                                                                                                                                                         | Proposed owner                            | Mode                              | Cross-links                  |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- | --------------------------------- | ---------------------------- |
| Run manifest            | `RunManifest`, `Anchors`, `PlayerSpec`, `Source`; `src/gptnt/cli/run/manifest.py`, `src/gptnt/players/specification.py`, `src/gptnt/experiments/ledger/base.py`, `runs/_template.yaml`       | `reference/configuration/run-manifest.md` | H+G                               | P5, P6, C2, C4               |
| Player profile          | `PlayerCapabilities`, `PlayerIdentity`, `ImageDimensions`, Pydantic AI `UsageLimits`, model settings, and the observation-processing subtree; `configs/player.yaml`, `configs/player/*.yaml` | `reference/configuration/players.md`      | H+G and H+E                       | P3, C3                       |
| Provider profile        | Provider, endpoint, client, API key, and headers; `configs/player/provider/*.yaml`                                                                                                           | `reference/configuration/providers.md`    | H+E                               | P3, provider troubleshooting |
| Suite                   | `Suite`, `SuiteMatchup`, `PlayerProtocol`, `ManualProfile`, `PairingType`; `configs/suites/*.yaml` and their implementation modules                                                          | `reference/configuration/suites.md`       | H+G                               | P5, C3, C4, C7               |
| Mission recipe          | `MissionGenerator`, `MissionGeneratorConfig`; `configs/missions/recipes/single_module.yaml`                                                                                                  | `reference/configuration/missions.md`     | H+G                               | P5, C2, C4                   |
| Materialised mission    | `KtaneMissionSpec`; `configs/missions/*/*.json`, `src/gptnt/ktane/mission_spec.py`                                                                                                           | `reference/configuration/missions.md`     | H+G                               | P5, C2                       |
| Manual profile          | `ManualProfile`, `OfficialDocument`, `KtaneContentDocument`, `KtaneContentAppendix`, `LocalDocument`; `configs/manual/*.yaml`, `src/gptnt/ktane/manuals/profile.py`                          | `reference/configuration/manuals.md`      | H+G                               | P4, C7                       |
| Manual source pins      | `ManualSources`, `KtaneContentSource`, `KtaneContentCatalogSource`, `OfficialManualSource`, `OfficialPageRange`; `configs/manual/sources.toml`, `src/gptnt/ktane/manuals/sources.py`         | `reference/configuration/manuals.md`      | H+G                               | P4, C7                       |
| Module registry         | `ModuleRegistry`, `ModuleFacts`; `configs/module_registry.yaml`, `src/gptnt/ktane/state/module_registry.py`                                                                                  | `reference/configuration/modules.md`      | H+G                               | C2, C7                       |
| Anchor defaults         | `configs/anchors.yaml`, represented through `Anchors`                                                                                                                                        | `reference/configuration/run-manifest.md` | H+G                               | P5, C4                       |
| Hydra suite composition | `configs/suite_generator.yaml`, `configs/hydra/default.yaml`; `src/gptnt/experiments/suite/generate.py`, `compose.py`, `src/gptnt/common/hydra.py`                                           | `reference/configuration/suites.md`       | H+V, collapsed contributor detail | C4                           |
| Runtime settings        | `Paths`, `RuntimeSettings`, `KtaneSettings`, `ObservabilitySettings`, `ServiceTimeouts`                                                                                                      | `reference/configuration/environment.md`  | H+G                               | P1, P6, C5                   |

### Hydra targets

Document local targets with generated detail only when their editable fields affect a reader:

- Player assembly: `PlayerService` as the assembly boundary,
  `NaughtyOutputBehaviourFeedbackGenerator`, `PlayerCapabilities`,
  `fingerprint_model_settings`, `PlayerIdentity`, `ExperimentPlayerRecorder`, `ActionPredictor`,
  `ObservationHandler`, `ImageResizer`, `SetOfMarksHandler`, `AnnotationTextParams`,
  `AnnotationBackgroundParams`, and `MaskDrawingParams`.
- Local player variants: `ImageDimensions`, the included dummy model classes, and local image
  resizer overrides.
- Suite composition: `Suite`, `PlayerProtocol`, `SuiteMatchup`, and `ManualProfile`.
- Mission recipes: `MissionGenerator` and `MissionGeneratorConfig`.
- Provider configuration: `cached_retrying_async_http_client` where the Google and gateway
  profiles use it.

The evidence is `configs/player.yaml`, `configs/player/*.yaml`, `configs/player/provider/*.yaml`,
`configs/suites/*.yaml`, and `configs/missions/recipes/*.yaml`.

Name these external targets locally, then link to their official documentation instead of
generating their APIs:

- `pydantic_ai.Agent`, `UsageLimits`, and `ModelSettings`.
- `AnthropicModel`, `GoogleModel`, `GoogleModelSettings`, `OpenAIChatModel`, and
  `OpenAIChatModelSettings`.
- `AnthropicProvider`, `AzureProvider`, `GoogleProvider`, the gateway provider, and
  `OpenAIProvider`.
- `anthropic.AsyncAnthropicFoundry` and `openai.AsyncOpenAI`.

### Templates

| Template                        | Contract and owner                                                                                                                  |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `runs/_template.yaml`           | Canonical run-manifest template; `reference/configuration/run-manifest.md`                                                          |
| `configs/suites/_template.yaml` | Suite authoring template; `reference/configuration/suites.md`                                                                       |
| `configs/player.yaml`           | Base Hydra player template inherited by player profiles; `reference/configuration/players.md`                                       |
| `PLAYER_TEMPLATE`               | Rendered by `gptnt new player`; command-owned implementation in `src/gptnt/cli/player/_templates.py`; not a supported Python import |
| `PROVIDER_TEMPLATE`             | Rendered by `gptnt new provider`; same ownership and support decision                                                               |

Existing player, provider, suite, and manual configurations are worked examples. They do not need
separate schema pages.

### Environment variables

The owner is `reference/configuration/environment.md`. Use a hand-written table grouped by purpose,
then generate local settings fields where they add types, defaults, or constraints.

Application variables:

- Paths: `CONFIGS`, `EXPERIMENT_SPECS_DIR`, `EXPERIMENT_RECORDER_OUTPUTS`,
  `EXPERIMENT_RECORDER`, `EXPERIMENTS_DB`, `STATICS_OUTPUTS`, `SUBMISSIONS_DIR`.
- Runtime endpoints: `GPTNT_EM_HOST`, `GPTNT_EM_PORT`, `REDIS_DSN`.
- Submission identity: `SUBMITTER`.
- Display requirement: `DISPLAY`.

Observability variables:

- `OBSERVABILITY_ENABLE_METRICS`
- `OBSERVABILITY_INSTRUMENT_FASTAPI`
- `OBSERVABILITY_INSTRUMENT_FASTSTREAM`
- `OBSERVABILITY_INSTRUMENT_HTTPX`
- `OBSERVABILITY_INSTRUMENT_PYDANTIC_AI`
- `OBSERVABILITY_INSTRUMENT_REDIS`
- `OBSERVABILITY_CAPTURE_SPAN_TIMINGS`
- `OTEL_EXPORTER_OTLP_ENDPOINT`
- `OTEL_RESOURCE_ATTRIBUTES`

KTANE variables:

- `KTANE_PLAYER_SETTINGS_FILE_NAME`
- `KTANE_PROGRESSION_FILE_NAME`
- `KTANE_WINDOWS`, `KTANE_MAC`, `KTANE_LINUX`
- `KTANE_GAME_WIDTH`, `KTANE_GAME_HEIGHT`, `KTANE_GAME_SPEED`
- `KTANE_MUSIC_VOLUME`, `KTANE_SFX_VOLUME`, `KTANE_LANGUAGE_CODE`

`ServiceTimeouts` has no prefix. Pydantic Settings therefore accepts the uppercase form of each
field name:

- `HEARTBEAT_REPEAT_INTERVAL`, `HEARTBEAT_CHECK_INTERVAL`, `HEARTBEAT_EXPIRATION`
- `TOMBSTONE_EXPIRATION`, `GAME_STATE_INTERVAL`
- `GET_BOMB_STATE_TIMEOUT`, `GET_OBSERVATION_TIMEOUT`
- `UPDATE_METRICS_INTERVAL`, `CONFIGURE_SERVICES_TIMEOUT`, `RUN_FORWARD_PASS_TIMEOUT`
- `REDIS_RPC_TIMEOUT`, `MAXIMUM_EXPERIMENT_DURATION`
- `SESSION_STATE_WATCHER_INTERVAL`, `GAME_REQUEST_TIMEOUT`

External integration variables should be named with their local effect and linked to the system
that defines them:

- W&B: `WANDB_ENTITY`, `WANDB_PROJECT`, `WANDB_MODE`.
- Provider examples: `ANTHROPIC_API_KEY`, `AZURE_OPENAI_API_KEY`,
  `ANTHROPIC_FOUNDRY_API_KEY`, `VLLM_API_KEY`, `CF_ACCESS_CLIENT_ID`,
  `CF_ACCESS_CLIENT_SECRET`.
- Submission and CI: `GITHUB_TOKEN`. CI supplies `GITHUB_STEP_SUMMARY`.
- Collector deployment: `LOGFIRE_TOKEN`.

Do not attempt to reproduce every provider variable defined by Pydantic AI. Link to its provider
documentation.

Exclude these from user-authored configuration:

- `GPTNT_MANUAL_ARTIFACTS` is populated by `gptnt run` for player processes.
- `GAME_WIDTH`, `GAME_HEIGHT`, `STREAMLIT_THEME_BASE`, `TESTING`, `REDIS_HOSTS`, and
  `GIT_NO_LAZY_FETCH` belong to child processes, the dashboard, tests, deployment, or subprocess
  behaviour.
- `APPDATA` is an operating-system convention used to derive the Windows path.
- `YOUR_ENDPOINT_API_KEY` appears only as a template placeholder.

## Persisted files and schemas

| Format                         | Contract and compatibility                                                                                                                          | Evidence                                                                        | Proposed owner                                         | Mode | Cross-links                   |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------ | ---- | ----------------------------- |
| Run manifest YAML              | `RunManifest`; schema version 2                                                                                                                     | `runs/_template.yaml`, `src/gptnt/cli/run/manifest.py`                          | `reference/files/run-manifest.md`                      | H+G  | P5, configuration counterpart |
| Suite YAML                     | Hydra-composed `Suite`; no format version                                                                                                           | `configs/suites/*.yaml`, `src/gptnt/experiments/suite/compose.py`               | `reference/files/suite-definitions.md`                 | H+G  | P5, C4                        |
| `suites.lock` TOML             | `SuiteLock`; version 2; repeated suite and mission records                                                                                          | `src/gptnt/experiments/suite/lock.py`                                           | `reference/files/suite-lock.md`                        | H+G  | `suite freeze`, P9, C4        |
| Manual profile YAML            | Discriminated document union; no format version                                                                                                     | `configs/manual/*.yaml`, `src/gptnt/ktane/manuals/profile.py`                   | `reference/files/manual-inputs.md`                     | H+G  | P4, C7                        |
| `sources.toml`                 | `ManualSources`; version 1                                                                                                                          | `configs/manual/sources.toml`, `src/gptnt/ktane/manuals/sources.py`             | `reference/files/manual-inputs.md`                     | H+G  | P4, C7                        |
| Materialised mission JSON      | Aliased `KtaneMissionSpec`; no format version                                                                                                       | `configs/missions/*/*.json`, `src/gptnt/ktane/mission_spec.py`                  | `reference/files/missions.md`                          | H+G  | `generate-missions`, C2       |
| Experiment-spec JSON           | One `ExperimentSpec` per attempt-name file; no format version                                                                                       | `src/gptnt/experiments/spec.py`                                                 | `reference/files/experiment-specifications.md`         | H+G  | `generate`, `run`, C2         |
| Player-record Parquet          | Format version 3; `ExperimentStep` rows; `RecordFooter`; footer keys `footer`, `format_version`, `session_id`, `player_uuid`; atomic `.tmp` sibling | `src/gptnt/experiments/recorder/parquet.py`, `src/gptnt/experiments/models.py`  | `reference/files/player-records.md`                    | H+G  | P6, P7, C6                    |
| Observation pickle             | Dill-encoded `Observation`; unstable intermediate                                                                                                   | player recording and input code                                                 | Contributor note in `reference/files/output-layout.md` | H+V  | Runtime recording             |
| Static prediction JSON         | `prediction_<index>.json`; index plus model output; no format version                                                                               | `src/gptnt/statics/run.py`, `src/gptnt/statics/model.py`                        | `reference/files/statics.md`                           | H+G  | P8, C6                        |
| Static metrics JSON            | Task-dependent `dict[str, dict[str, Any]]`; no format version                                                                                       | `src/gptnt/statics/scorers.py`, `src/gptnt/statics/run.py`                      | `reference/files/statics.md`                           | H+V  | P8, C6                        |
| Static run metadata JSON       | `StaticsRunMetadata`, `StaticsIdentity`, capabilities, provenance; no format version                                                                | `src/gptnt/statics/run_metadata.py`                                             | `reference/files/statics.md`                           | H+G  | P8, C6                        |
| How-do-you JSON                | Module-to-attempt mapping with `prompt` and `response`; no metadata or metrics                                                                      | `src/gptnt/cli/statics/how_do_you.py`                                           | `reference/files/statics.md`                           | H+V  | P8                            |
| Submission bundle              | `submission.yaml` version 2; discriminated interactive or statics manifest                                                                          | `src/gptnt/cli/submission/_schema.py`, `_bundle.py`                             | `reference/files/submission-bundles.md`                | H+G  | P9, C4, C6                    |
| Interactive submission payload | `experiments.parquet` using `SubmissionExperiment`, plus reduced `suite.lock`                                                                       | submission bundle modules                                                       | `reference/files/submission-bundles.md`                | H+G  | P9, C4, C6                    |
| Statics submission payload     | Copied `metrics.json`                                                                                                                               | submission bundle modules                                                       | `reference/files/submission-bundles.md`                | H+V  | P9, C6                        |
| Manual artifact                | Content-addressed directory with `manifest.json`, `handbook.pdf`, and numbered text and PNG pages; no format version                                | `src/gptnt/ktane/manuals/artifacts.py`                                          | `reference/files/manual-artifacts.md`                  | H+G  | P4, C7                        |
| Span-timing JSONL              | One file per service process; no format version                                                                                                     | `src/gptnt/observability/span_timing.py`, `src/gptnt/cli/experiments/timing.py` | `reference/files/span-timings.md`                      | H+V  | `timing`, C5                  |
| KTANE settings XML             | `playerSettings.xml`, `progression.xml`, timestamped backups; external game formats                                                                 | `src/gptnt/ktane/game_settings.py`                                              | Environment and game reference                         | H+V  | P1, game troubleshooting      |
| Process logs                   | Plain run-specific process logs                                                                                                                     | `src/gptnt/common/paths.py`, run pipeline                                       | `reference/files/output-layout.md`                     | H+V  | P6, troubleshooting           |
| W&B and Weave data             | External persistence contracts                                                                                                                      | ledger, recorder, statics upload call sites                                     | Integration sections with external links               | H+E  | P7, P8, C6                    |

Materialised mission JSON uses aliases including `ruleSeed`, `timeLimit`, `numStrikes`,
`optWidgets`, `needyTime`, `isFront`, `timeScale`, and `timeStepSize`. Player-record format version 2
is rejected as the older record artifact. Local completion is derived from grouped Parquet records,
not stored in another local format. Manual source downloads are cache artifacts rather than stable
file contracts.

### DuckDB

The owner is `reference/files/duckdb.md`. Use H+G and link to `build-db`, `results`, `analyse`, P7,
and C6.

The database has two base tables and no views:

- `experiment_step`: `step`, `timestamp`, `role`, `session_id`, `player_uuid`, `player_name`,
  `output`, `raw_output`, `thoughts`, `input_messages`, `new_messages`, `bomb_state`,
  `observation`, `usage`, `num_prompt_truncations`, `error_type`, `is_reflection`.
- `experiment_summary`: declared outcome, provenance, suite, mission, protocol, player, identity,
  timing, crash, and capability fields from `ExperimentSummary`. Persisted computed fields include
  `is_solved`, `is_strike_out`, `is_timed_out`, `is_detonated`, `fingerprint`, `attempt_name`,
  `seed`, `communication_style`, `modules`, the two capability fingerprints,
  `defuser_has_manual`, and `mission_key`.

Evidence is `src/gptnt/experiments/db/schema.py`, `src/gptnt/experiments/models.py`, and
`src/gptnt/experiments/db/ingest.py`. The database has no metadata or version table. Ingestion checks
the schema structure. `.duckdb.wal` is transient.

### Output directory layout

The owner is `reference/files/output-layout.md`. Use a hand-written tree backed by `Paths`, then
link each subtree to its format page.

```text
storage/
  ktane/
  prompts/
output/
  logs/run_<run-output-name>/
  observations/
  experiments.duckdb
  experiment_specs/<manifest-stem>/
  submissions/<date>_<display-slug>_<capability-fingerprint>_<target>_<version>/
  manual_cache/
    artifacts/<sha256>/
    sources/
  experiment_recorder_outputs/<timestamp>/
    span_timings/<service>-<pid>.jsonl
  <task>_predictions/<model>/
  how_do_you/<model>.json
```

`EXPERIMENT_RECORDER_OUTPUTS` can replace the timestamped recorder directory. Evidence is
`src/gptnt/common/paths.py`, the run pipeline, the statics runner, submission bundle naming, and
manual artifact storage.

## Supported Python integration decisions

Include an object in generated Python reference or in a generated configuration or file section
that identifies its supported import, while retaining selected contributor rendering for excluded
implementation objects.

### Include

| Objects                                                                                                                                                        | Reason                                                                           | Proposed owner                                                   | Mode and cross-links                      |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ----------------------------------------- |
| `PlayerCapabilities`, `PlayerIdentity`, `PlayerProtocol`, `PlayerSpec`, and their role, type, communication, and thinking aliases                              | Expected player and configuration inputs; persisted identities                   | `reference/python/player-interfaces.md`                          | H+G; P3, C3                               |
| Player output actions, action unions, `GameActionType`, `RelativeCoordinate`, `KtaneBaseAction`, `KtaneGameplayInput`                                          | Custom action and model-output boundary                                          | `reference/python/actions-and-observations.md`                   | H+G; P3, C3                               |
| Coordinate and set-of-marks location models and aliases                                                                                                        | Part of the action contract                                                      | `reference/python/actions-and-observations.md`                   | H+G; P3, C3                               |
| `Observation`, `ObservationHandler`                                                                                                                            | Processor and player boundary; Hydra target                                      | `reference/python/actions-and-observations.md`                   | H+G; P3, C3                               |
| `ActionPredictor`, `AgentCallResult`, `DispatchedAgentCallResult`                                                                                              | Configured player integration boundary and result objects                        | `reference/python/player-interfaces.md`                          | H+G; P3, C3                               |
| `ImageDimensions`, `ImageResizer`, `SetOfMarksHandler`, drawing parameter objects                                                                              | User-configured processors                                                       | `reference/python/processors.md`                                 | H+G; P3                                   |
| `NaughtyOutputBehaviourFeedbackGenerator`, local and W&B experiment recorders                                                                                  | Exposed Hydra targets whose constructor compatibility affects user configuration | Player integration page                                          | H+G; P3, C6                               |
| `Suite`, `SuiteMatchup`, `SuiteIdentity`, `Pairing`, `PairingGenerator`, `MissionGenerator`, `MissionGeneratorConfig`, `ExperimentGenerator`, `ExperimentSpec` | Generation, configuration, and persisted contracts                               | `reference/python/experiment-generation.md`                      | H+G; P5, C2, C4                           |
| `KtaneMissionSpec`, manual profile and source models, `ManualArtifact`, `SuiteLock` and its entries                                                            | Configuration and file contracts                                                 | Their configuration and file pages, cross-linked from generation | H+G; P4, P5, C4, C7                       |
| `CompletionLedger`, `ExperimentStatus`, `LocalLedger`, `Source`, `filter_experiments`, `resolve_ledger`                                                        | Explicit `gptnt.experiments.ledger` package API and completion boundary          | `reference/python/completion-ledgers.md`                         | H+G; P6, P7, C6                           |
| `BenchmarkIntegrityError`, `Provenance`, `check_benchmark_integrity`, `git_sha`, `gptnt_version`, `is_valid_version`                                           | Explicit `gptnt.provenance` package API and persisted compatibility contract     | `reference/python/provenance.md`                                 | H+G; C6                                   |
| `Conversation`                                                                                                                                                 | Explicit `gptnt.players.conversation` package re-export                          | `reference/python/player-interfaces.md`                          | H+G; P3, C3; provisional support decision |

### Exclude from the supported extension API

| Objects or modules                                                                                                                                                                          | Reason and alternative coverage                                                                                                                     |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gptnt.interactive.orchestration` objects                                                                                                                                                   | They supervise `gptnt run`. Render selected objects in contributor runtime. The explicit package re-export still requires coordinator confirmation. |
| `gptnt.cli.checks` re-exports                                                                                                                                                               | Cross-CLI report and rendering machinery with no external-use evidence.                                                                             |
| `PlayerService`, `GameService`, `ExperimentManager`, their clients, registries, heartbeats, and RPC classes                                                                                 | Current runtime implementation. Include only in contributor tracing.                                                                                |
| Reasoning-parser implementations and the exception-recovery chain                                                                                                                           | Current player internals. No supported plug-in protocol or Hydra selection boundary is declared.                                                    |
| Included dummy model classes                                                                                                                                                                | Packaged examples and test players, not integration contracts.                                                                                      |
| DuckDB type markers and schema-generation mixins                                                                                                                                            | Persistence implementation.                                                                                                                         |
| Database connection, ingest, extraction, and W&B reconciliation helpers                                                                                                                     | Command and runtime implementation.                                                                                                                 |
| Manual compiler, downloader, and resolution helpers                                                                                                                                         | Behavior is supported through commands, configuration, and manual artifacts.                                                                        |
| Statics runner and scorer types                                                                                                                                                             | Static tasks are registered as fixed CLI commands. `gptnt.statics` exports no extension protocol.                                                   |
| `common._run_once`, `interactive.services._exceptions`, `interactive.services.registry._metrics`, `cli.player._templates`, `cli.manual._selection`, `cli.run._monitor`, `cli.run._pipeline` | The source-layout audit made these modules private. Exclude them from supported imports.                                                            |
| Broader dashboard, runtime, and cross-CLI modules                                                                                                                                           | The source-layout audit deferred their privacy decisions. A public filename alone does not include them.                                            |

`Conversation` should remain provisional until the coordinator confirms that its package re-export
is intentional support. The `interactive.orchestration` re-export conflicts with its
implementation-only role; resolve that source-layout question separately from documentation
rendering.

## Contributor-only runtime coverage

Every page in this section must state that it describes the current implementation rather than a
supported extension interface.

| Subsystem and selected contracts                                                                                                                                                                    | Evidence                                                                          | Proposed owner                                  | Presentation and cross-links                                                                |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Run orchestration: diagnosis, manual preparation, process spawn, queue submission, monitoring, termination; `ProcessOrchestrator`, `TrackedProcess`, `ProcessStatus`, spawn functions, run pipeline | `src/gptnt/cli/run/_pipeline.py`, `src/gptnt/interactive/orchestration/*`         | `reference/runtime/run-orchestration.md`        | Hand-written sequence diagram plus selected generated objects; P6, C5                       |
| Experiment manager: FastAPI lifespan, registry, matchmaking, sessions, sync and async runners; `GET /health`, `POST /add-specs`, `GET /active`                                                      | `src/gptnt/interactive/services/experiment_manager/*`                             | `reference/runtime/experiment-manager.md`       | Lifecycle and state diagrams plus selected payload and state models; `submit`, `status`, C5 |
| Player service: configuration, messages, observation and input building, model pass, dispatch, feedback, reflection, recording, cleanup                                                             | `src/gptnt/interactive/services/player/*`                                         | `reference/runtime/player-service.md`           | Lifecycle diagram plus selected payload and state models; C3, player records                |
| Game service covers the KTANE process and HTTP client as well as the state monitor and Redis handlers                                                                                               | `src/gptnt/interactive/services/game/*`, `src/gptnt/ktane/client.py`              | `reference/runtime/game-service.md`             | Call-path diagram plus selected action, mission, and state models; C5, game troubleshooting |
| Service registry: manifests, readiness, state transitions, matching availability, expiry                                                                                                            | `src/gptnt/interactive/services/registry/*`                                       | `reference/runtime/service-registry.md`         | State diagram plus selected manifest and state objects; C5                                  |
| Heartbeats and tombstones: Redis hashes, expiry, sequence, uptime, process and host diagnostics, failure categories                                                                                 | `src/gptnt/interactive/services/heartbeat/*`                                      | `reference/runtime/heartbeats-and-rpc.md`       | Hand-written contract plus selected generated models; C5                                    |
| Redis RPC: request channels, exception-aware decoding, timeouts, player message channels                                                                                                            | `src/gptnt/interactive/services/rpc.py`, `broker.py`, `player/message_handler.py` | `reference/runtime/heartbeats-and-rpc.md`       | Hand-written channel and payload contract; C5                                               |
| Recording and completion covers the player recorder and footer finalisation together with local and W&B ledgers and database ingest                                                                 | `src/gptnt/experiments/recorder/*`, `ledger/*`, `db/ingest.py`                    | `reference/runtime/recording-and-completion.md` | Data-flow diagram with links to ledger and file schemas; P6, P7, C6                         |
| Manual preparation: profile selection, download, resolution, content-addressed compile, runtime artifact injection                                                                                  | `src/gptnt/cli/manual/*`, `src/gptnt/ktane/manuals/*`, run pipeline               | `reference/runtime/manual-preparation.md`       | Data-flow diagram; P4, C7                                                                   |
| Observability and timing: instrumentation presets, OTLP, service identity, span timing processor                                                                                                    | `src/gptnt/observability/settings.py`, `span_timing.py`, run pipeline             | `reference/runtime/observability.md`            | Hand-written subsystem overview plus selected settings; `timing`, C5                        |
| Dashboard read path: DuckDB load and extraction, Streamlit presentation and exports                                                                                                                 | `src/gptnt/app/*`, `src/gptnt/cli/analysis/launch.py`                             | Contributor subsection under results runtime    | Hand-written data flow; P7, C6                                                              |

Player RPC commands are `configure_for_experiment`, `forward_pass`, `stop`, `reset`, `reflection`,
`send_feedback`, and `get_state`. Game RPC commands are `advance_game_time`, `configure_game`,
`get_bomb_state`, `get_frames`, `get_game_state`, `go_to_main_menu`, `pause_game`, `send_action`,
`set_game_speed`, `stop_game`, and `unpause_game`.

RPC requests use `player:<uuid>:commands:<command>` and `game:<uuid>:commands:<command>`. Player
messages use `session:<session_id>:player:<role>:messages`. Heartbeats and tombstones use
`heartbeat:<service>:<uuid>` and `tombstone:<service>:<uuid>`.

## Omissions from the initial coverage map

The initial map in `documentation-site.md` needs these additions or explicit nesting decisions:

- CLI: `new`, `list`, `measure-tokens-per-image`, `generate-missions`, `suite freeze`, both manual
  commands, queue `submit`, `kill`, `status`, `cleanup-outputs`, `reconcile-wandb`, `build-db`,
  `analyse`, and `timing` are not individually visible.
- CLI: record the six groups and 21 nested leaf commands, not only the top-level categories.
- Configuration needs anchors and the module registry. It also needs Hydra composition, KTANE
  settings, service timeouts, observability settings, runtime endpoints, and generated command
  templates.
- Configuration: record the delegation policy for third-party provider targets and environment
  variables.
- Files need the run manifest and suite lock. They also need manual source pins, manual artifacts,
  span timings, observation pickle, how-do-you output, game XML, logs, caches, and W&B and Weave
  boundaries.
- Files: record schema versions in one compatibility table: run manifest 2, suite lock 2, player
  Parquet 3, submission manifest 2, and manual sources 1. State which other formats have no version.
- Database coverage must record both base tables and structural compatibility checks. It must also
  state that there are no views or database-version table.
- Python: add completion ledgers, provenance, manuals, suite locks, result objects, location types,
  and recorder targets.
- Python: decide whether the `Conversation` and `interactive.orchestration` package re-exports are
  supported interfaces.
- Runtime coverage needs run orchestration and recording and completion. It also needs manual
  preparation, observability and timing, and the dashboard read path.
- Output-layout coverage needs timestamped or pinned recorder directories and run logs. It also
  needs timing rows, content-addressed manual artifacts, statics output, and submission naming.

These omissions expand the verified initial map. They do not require one page per interface. Keep
the page grouping and progressive-exposure rules in `documentation-site.md`.
