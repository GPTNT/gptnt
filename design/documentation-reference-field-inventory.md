# Reference field documentation inventory

- Status: prioritised planning backlog
- Applies to: GPTNT v2 and later
- Evidence: v2 models, callers, serialisation, configuration examples, and focused tests
- Prose check: Vale reported zero findings

## Purpose

This file records implementation-backed candidates for field descriptions and object-level
reference explanations. It is an input to reference planning, source docstring work, and coverage
checks. It is not public documentation and does not make an object part of the supported Python
interface.

A field remains in this inventory only when its declaration does not convey necessary meaning,
units, provenance, lifecycle, relationships, indexing conventions, or hidden behaviour. Generated
types, defaults, literal values, and optionality must not be repeated in prose.

## P0: User-authored configuration and persisted schemas

### Run configuration

- `src/gptnt/cli/run/manifest.py:RunManifest.rooms`: Number of KTANE game-service processes started for concurrent experiments.
- `src/gptnt/cli/run/manifest.py:RunManifest.players`: Player roster whose `count` values determine how many player-service processes are started.
- `src/gptnt/cli/run/manifest.py:RunManifest.anchors`: Player configuration names used as fixed opponents by `with_best_*` suite pairings. Each name must also resolve from the roster.
- `src/gptnt/cli/run/manifest.py:RunManifest.observability`: Controls service instrumentation. `full` retains the configured instrumentation, `limited` retains Pydantic AI instrumentation with aggressive sampling, and `off` disables instrumentation.
- `src/gptnt/players/specification.py:PlayerCapabilities.usage_limits`: Pydantic AI request limits. GPTNT also uses the input-token limit when truncating conversation history.
- `src/gptnt/common/paths.py:Paths.root`: Base directory from which default configuration, storage, and output paths are derived. The default is the current working directory.

### Suite configuration and lock

- `src/gptnt/experiments/suite/core.py:Suite.name`: Suite identifier copied into lock entries, experiment specifications, results, and submission targets.
- `src/gptnt/experiments/suite/core.py:Suite.revision`: Comparability revision that must increase when the suite's measured content changes.
- `src/gptnt/experiments/suite/core.py:Suite.modality`: Sorted set of input modalities included in the suite configuration digest.
- `src/gptnt/experiments/suite/core.py:Suite.missions_path`: Repository-relative directory whose materialised mission files are included in the suite digest.
- `src/gptnt/experiments/suite/core.py:Suite.defuser_protocol`: Defuser access and action rules copied into every generated experiment specification.
- `src/gptnt/experiments/suite/core.py:Suite.expert_protocol`: Expert access and action rules copied into every generated non-solo experiment specification.
- `src/gptnt/experiments/suite/lock.py:MissionEntry.mission_key`: Identity derived from the mission and rule seeds plus the sorted component names.
- `src/gptnt/experiments/suite/lock.py:SuiteLockEntry.revision`: Frozen comparability revision in the append-only sequence for a suite name.
- `src/gptnt/experiments/suite/lock.py:SuiteLockEntry.suite_digest`: Digest recomputed from the frozen suite configuration and referenced mission bodies.
- `src/gptnt/experiments/suite/lock.py:SuiteLockEntry.gptnt_version`: Installed GPTNT version used when this suite revision was frozen.
- `src/gptnt/experiments/suite/lock.py:SuiteLockEntry.config`: JSON-form suite fields used to reconstruct the frozen suite. The value excludes the computed configuration digest.
- `src/gptnt/experiments/suite/lock.py:SuiteLock.suites`: Append-only frozen revisions for each suite.
- `src/gptnt/experiments/suite/lock.py:SuiteLock.missions`: Deduplicated mission bodies referenced by `mission_key` from frozen suites.

### Mission generation

- `src/gptnt/experiments/generation/missions.py:MissionGeneratorConfig.n_modules_min`: Inclusive lower bound for the number of components generated in each mission.
- `src/gptnt/experiments/generation/missions.py:MissionGeneratorConfig.n_modules_max`: Inclusive upper bound for the number of components generated in each mission.
- `src/gptnt/experiments/generation/missions.py:MissionGeneratorConfig.sample_from_modules`: Generates one sampled component set per seed when enabled and one mission per available module per seed when disabled.
- `src/gptnt/experiments/generation/missions.py:MissionGeneratorConfig.allow_repeat_module`: Allows random multi-module sampling to select components with replacement.
- `src/gptnt/experiments/generation/missions.py:MissionGeneratorConfig.min_optional_widgets`: Inclusive lower bound for the randomly generated optional-widget count.
- `src/gptnt/experiments/generation/missions.py:MissionGeneratorConfig.max_optional_widgets`: Inclusive upper bound for the randomly generated optional-widget count.
- `src/gptnt/ktane/mission_spec.py:KtaneMissionSpec.time_step_size`: Number of milliseconds advanced by each timestep command before the game pauses again.

### Manual sources

- `src/gptnt/manuals/sources.py:KtaneContentCatalogSource.url`: Download location for the aggregate catalog that maps module identifiers and languages to filenames.
- `src/gptnt/manuals/sources.py:KtaneContentSource.repository`: Git repository from which KtaneContent documents and assets are downloaded.
- `src/gptnt/manuals/sources.py:KtaneContentSource.commit`: Exact repository commit included in cache paths and artifact provenance.
- `src/gptnt/manuals/sources.py:KtaneContentSource.catalog`: Catalog used to resolve module identifiers and translated document filenames.
- `src/gptnt/manuals/sources.py:OfficialManualSource.version`: Manual version included in the cache location and artifact provenance.
- `src/gptnt/manuals/sources.py:OfficialManualSource.url`: Download location for the official manual in the configured language.
- `src/gptnt/manuals/sources.py:ManualSources.official_manual`: Official-manual sources keyed by language code.

### Experiment specifications and submissions

- `src/gptnt/experiments/spec.py:ExperimentSpec.mission_spec`: Exact bomb configuration played by this attempt.
- `src/gptnt/experiments/spec.py:ExperimentSpec.attempt`: Generator-assigned, one-based repeat index for the same mission and player pairing.
- `src/gptnt/experiments/spec.py:ExperimentSpec.suite_revision`: Frozen suite revision that defines comparability for this specification.
- `src/gptnt/experiments/spec.py:ExperimentSpec.suite_digest`: Digest of the frozen suite configuration and mission snapshot copied into this specification.
- `src/gptnt/experiments/spec.py:ExperimentSpec.manual_profile`: Ordered manual profile prepared for this experiment.
- `src/gptnt/experiments/spec.py:ExperimentSpec.defuser_name`: `player_name` assigned to the defuser role, not the player configuration name.
- `src/gptnt/experiments/spec.py:ExperimentSpec.expert_name`: `player_name` assigned to the expert role, not the player configuration name.
- `src/gptnt/cli/submission/_schema.py:SubmissionExperiment.final_bomb_state`: Terminal bomb state against which the outcome and mission pairing are validated.
- `src/gptnt/cli/submission/_schema.py:SubmissionExperiment.defuser_usage`: Sum of Pydantic AI usage recorded by defuser steps in this execution.
- `src/gptnt/cli/submission/_schema.py:SubmissionExperiment.expert_usage`: Sum of Pydantic AI usage recorded by expert steps in this execution.
- `src/gptnt/cli/submission/_schema.py:SubmissionPlayer.identity`: Leaderboard attribution loaded from the player configuration for these capabilities.
- `src/gptnt/cli/submission/_schema.py:Submission.submission_id`: Identifier derived from the run date, player name, target, and abbreviated capability fingerprint.
- `src/gptnt/cli/submission/_schema.py:Submission.run_date`: Earliest included experiment start for interactive results, or the bound output-set start for statics results.
- `src/gptnt/cli/submission/_schema.py:Submission.provenance`: Benchmark release provenance shared by every payload row.

## P1: Results, analysis, and supported Python objects

### Experiment records

- `src/gptnt/experiments/instance.py:ExperimentInstance.session_id`: Identifier shared by the game and player records that belong to one execution.
- `src/gptnt/experiments/instance.py:ExperimentInstance.defuser_uuid`: Player-service process assigned to the defuser role.
- `src/gptnt/experiments/instance.py:ExperimentInstance.expert_uuid`: Player-service process assigned to the expert role.
- `src/gptnt/experiments/instance.py:ExperimentInstance.game_uuid`: Game-service process assigned to this execution.
- `src/gptnt/experiments/instance.py:ExperimentInstance.start_time`: Instant used as the origin for relative step timestamps.
- `src/gptnt/experiments/models.py:ExperimentStep.step`: One-based counter within one player record. Reflection rows also increment it.
- `src/gptnt/experiments/models.py:ExperimentStep.session_id`: Execution identifier used to join rows recorded by different players.
- `src/gptnt/experiments/models.py:ExperimentStep.output`: Parsed player action that was dispatched for this step.
- `src/gptnt/experiments/models.py:ExperimentStep.raw_output`: Unparsed model response retained by parsing or recovery.
- `src/gptnt/experiments/models.py:ExperimentStep.thoughts`: Reasoning text extracted separately from the player action.
- `src/gptnt/experiments/models.py:ExperimentStep.input_messages`: Prior conversation rendered as message history before the current model call.
- `src/gptnt/experiments/models.py:ExperimentStep.new_messages`: Request and response messages added by the current model call.
- `src/gptnt/experiments/models.py:ExperimentStep.observation`: Captured observation, represented by its temporary serialised-file path before record rebuilding.
- `src/gptnt/experiments/models.py:ExperimentStep.num_prompt_truncations`: Cumulative number of oldest non-pinned conversation entries omitted from model requests.
- `src/gptnt/experiments/models.py:ExperimentStep.error_type`: Response-error classifications recorded by parsing or recovery.
- `src/gptnt/experiments/models.py:StepRecordsMetricsMixin.step_records`: Step rows sorted by relative timestamp before aggregate metrics are calculated.
- `src/gptnt/experiments/models.py:ExperimentPlayerRecord.is_hard_crash`: Indicates that a service failure ended the experiment execution.
- `src/gptnt/experiments/models.py:ExperimentOutcome.seconds_remaining`: Bomb-timer seconds at terminal state. DuckDB stores the value as `timer_seconds`.
- `src/gptnt/experiments/models.py:ExperimentRecord.step_records`: Rows aggregated from all player records and sorted by timestamp.
- `src/gptnt/experiments/recorder/parquet.py:RecordFooter.instance`: Execution metadata shared by every row in one player's Parquet file.
- `src/gptnt/experiments/recorder/parquet.py:RecordFooter.final_bomb_state`: Last bomb state captured for the execution.
- `src/gptnt/experiments/recorder/parquet.py:RecordFooter.role`: Player role whose step rows are stored in the file.

### Statics

- `src/gptnt/statics/model.py:ModelOutput.usage`: Non-zero token-usage counts flattened from Pydantic AI usage for this prediction.
- `src/gptnt/statics/model.py:ModelOutput.model`: Provider model name resolved for this prediction.
- `src/gptnt/statics/model.py:ModelOutput.output`: Parsed task output before task-specific score normalisation.
- `src/gptnt/statics/model.py:ModelOutput.error`: Model-response validation classifications produced by parsing or recovery.
- `src/gptnt/statics/model.py:ModelOutput.exception`: Structured traceback for an exception that prevented prediction.
- `src/gptnt/statics/run_metadata.py:StaticsIdentity.requested_revision`: Branch, tag, or commit supplied to the dataset loader before pin resolution.
- `src/gptnt/statics/run_metadata.py:StaticsIdentity.resolved_revision`: Concrete dataset commit resolved before prediction.
- `src/gptnt/statics/run_metadata.py:StaticsRunMetadata.run_date`: Output-set start instant bound before the first prediction and preserved on resume.
- `src/gptnt/statics/run_metadata.py:StaticsRunMetadata.provenance`: GPTNT release provenance captured before prediction.

### Player and KTANE data

- `src/gptnt/players/result.py:AgentCallResult.new_messages`: Request and response messages added by the call. Validators forbid tool parts and require a final response message.
- `src/gptnt/players/result.py:AgentCallResult.ai_response_error`: Response-error classifications retained after parsing or recovery.
- `src/gptnt/players/result.py:DispatchedAgentCallResult.dispatched_at`: Instant at which output dispatch starts and from which the recorder derives the relative step timestamp.
- `src/gptnt/players/observation_handler.py:Observation.frames`: Ordered PNG game frames before the final frame is replaced by its set-of-marks version.
- `src/gptnt/players/observation_handler.py:Observation.segm_mask`: PNG segmentation mask aligned with the final game frame.
- `src/gptnt/players/observation_handler.py:Observation.som_image`: Final frame after optional set-of-marks processing and resizing. This image is sent to the defuser model.
- `src/gptnt/ktane/state/modules.py:BaseModuleState.index`: Zero-based slot index on one bomb face.
- `src/gptnt/ktane/state/modules.py:BaseModuleState.on_front`: Adds six to the face-local index when deriving `module_location`.
- `src/gptnt/ktane/state/modules.py:InteractiveModuleState.in_focus`: The first focused module determines `zoomed_in_component`.
- `src/gptnt/ktane/state/bomb.py:BombState.max_strikes`: Strike count at which the terminal outcome is classified as a strikeout.
- `src/gptnt/ktane/state/bomb.py:BombState.timer_module`: Timer state from which `seconds_remaining` and timeout outcomes are derived.

## P2: Maintainer-facing runtime contracts

- `src/gptnt/common/runtime_settings.py:RuntimeSettings.em_host`: Experiment-manager host read from `GPTNT_EM_HOST` by runtime clients.
- `src/gptnt/common/runtime_settings.py:RuntimeSettings.em_port`: Experiment-manager HTTP port read from `GPTNT_EM_PORT` by runtime clients.
- `src/gptnt/common/runtime_settings.py:RuntimeSettings.redis_dsn`: Redis connection string read from `REDIS_DSN` by runtime services.
- `src/gptnt/observability/settings.py:ObservabilitySettings.instrument_httpx`: Enables HTTPX capture of request headers and bodies. Response bodies remain excluded.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.heartbeat_repeat_interval`: Seconds between heartbeats emitted by each service.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.heartbeat_check_interval`: Seconds between registry scans for expired service heartbeats.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.heartbeat_expiration`: Seconds after the last heartbeat before the registry treats a service as expired.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.tombstone_expiration`: Seconds for which a shutdown tombstone remains in Redis.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.game_state_interval`: Seconds between game-state polls.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.get_bomb_state_timeout`: Seconds allowed for one bomb-state RPC.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.get_observation_timeout`: Seconds allowed for one game-observation RPC.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.update_metrics_interval`: Seconds between service-metric updates.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.configure_services_timeout`: Seconds allowed to configure all services assigned to an execution.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.run_forward_pass_timeout`: Seconds allowed for one player forward pass.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.redis_rpc_timeout`: Seconds allowed for one Redis RPC response.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.maximum_experiment_duration`: Seconds before the runner forcibly stops an experiment.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.session_state_watcher_interval`: Seconds between session-watcher polls of service state.
- `src/gptnt/interactive/services/timeouts.py:ServiceTimeouts.game_request_timeout`: Seconds allowed for one game-service HTTP request.
- `src/gptnt/interactive/services/heartbeat/base.py:BaseHeartbeat.timestamp`: Wall-clock instant at which this heartbeat was created.
- `src/gptnt/interactive/services/heartbeat/base.py:BaseHeartbeat.ready_state`: Service eligibility for work, independent of the phase-specific state.
- `src/gptnt/interactive/services/heartbeat/player.py:PlayerHeartbeat.capabilities`: Capabilities advertised at registration and serialised inside the Redis heartbeat hash.
- `src/gptnt/interactive/services/heartbeat/tombstone.py:ServiceTombstone.uptime_seconds`: Seconds from heartbeat-broadcaster creation until service shutdown.
- `src/gptnt/interactive/services/heartbeat/watcher.py:ServiceExpiredContext.tombstone`: Shutdown record retained in Redis when expiration was diagnosed.
- `src/gptnt/interactive/services/heartbeat/watcher.py:ServiceExpiredContext.heartbeat_key_ttl`: Raw Redis TTL at diagnosis. A value of `-2` means that the key was absent.
- `src/gptnt/interactive/services/heartbeat/watcher.py:ServiceExpiredContext.remaining_heartbeat_fields`: Hash fields still present in the heartbeat key when expiration was diagnosed.
- `src/gptnt/interactive/services/heartbeat/watcher.py:ServiceExpiredContext.last_heartbeat_seq`: Sequence number from the last heartbeat accepted into the registry manifest.

## Object-level documentation gaps

- Explain how a frozen suite and its missions flow through specification generation, execution, per-player recording, summarisation, and submission.
- Explain the three suite identities together. `config_digest` excludes the suite name, revision, and mission bodies. `suite_digest` includes the frozen configuration and missions. `revision` is the human-managed comparability boundary.
- State the `ExperimentSpec` invariant that expert protocol and expert name must either both be present or both be absent.
- State the `PlayerCapabilities` cross-field rules for thinking method, structured output, schema inclusion, coordinate mode, and image scaling.
- Explain the manual pipeline from ordered profile documents through pinned source resolution and resolved provenance to a content-addressed artifact.
- Explain that all effective manual documents must use the requested language and that only default rule seed 1 is supported. These checks occur during resolution rather than model validation.
- Explain requested dataset revision versus resolved commit, metadata creation before the first prediction, and resume rejection when prediction data exists without metadata.
- Explain the difference between `ModelOutput.error`, `ModelOutput.exception`, unnormalised `output`, and task-specific scored output.
- Explain the coordinated runtime state machines for service readiness, player and game phase, registry allocation, and experiment lifecycle.
- Explain the valid terminal outcomes together. Completed records have `is_hard_crash` set to false and an outcome of solved, timeout, or strikeout. A generic detonated state alone is not a valid completed outcome.

## Exclusions and decisions

- Standard Griffe sees attribute string docstrings but does not expose Pydantic `Field(description=...)` values. Validate the `griffe-pydantic` integration before adding duplicate source prose.
- `Suite.modality` is sorted, deduplicated, and included in fingerprints, but v2 execution does not enforce it against player capabilities. Documentation must not claim enforcement.
- `KtaneMissionSpec.time_scale` is overwritten by `KtaneSettings.game_speed` when a mission starts. Its reference wording requires a behavior decision first.
- Generated `ExperimentSpec.attempt` values are one-based, but the model does not enforce that constraint.
- Most KTANE module and widget payload fields mirror the external mod contract or are clear from their declaration. A detailed schema page may still require upstream-contract verification, but these fields should not receive repetitive one-line docstrings.
- Private download plans, timing rows, submission sessions, UI state, drawing geometry, RPC dependency containers, and forwarding wrappers remain excluded unless the public API decision promotes them.
- The public API allowlist may move experiment-record models from Python API reference into file-format reference. Their persisted semantics require documentation in either location.
