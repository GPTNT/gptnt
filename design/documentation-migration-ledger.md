# Documentation migration ledger

- Status: checked Stage 1 planning evidence
- Applies to: GPTNT v2 and later
- Public site status: not published
- Sources: `origin/v2`, committed `more-docs`, and the `more-docs` working tree inspected on
  23 August 2026

## Purpose

This ledger assigns every existing documentation section to a destination in the planned site. It
records whether the destination should adopt, rewrite, split, or reject each source block. The v2
implementation and tests determine behaviour. The `more-docs` branch supplies candidate prose and
presentation choices only.

The ledger is an implementation input. It does not approve wording that has not been checked on the
target page, and it does not replace the reference coverage inventory.

## Evidence keys

| Key       | Evidence checked                                                                                  |
| --------- | ------------------------------------------------------------------------------------------------- |
| `DOC`     | Current public v2 pages and `zensical.toml` navigation                                            |
| `CLI`     | Cyclopts registrations, command implementations, rendered help, and CLI tests                     |
| `CFG`     | `RunManifest`, player and provider configuration, settings, templates, and configuration tests    |
| `SPEC`    | Suites, specifications, instances, missions, generation, and suite-lock implementation and tests  |
| `RESULT`  | Parquet records and footers, outcomes, DuckDB, completion ledgers, and provenance                 |
| `RUNTIME` | Run orchestration, services, registries, heartbeats, RPC, and their tests                         |
| `MANUAL`  | Manual profiles, sources, artifacts, cache lifecycle, commands, and tests                         |
| `STATIC`  | Static commands, shared options, outputs, metadata, scoring, and submission inputs                |
| `SUBMIT`  | Submission schema, bundle builder, validation, remote submission, release workflow, and tests     |
| `SITE`    | Documentation specification, Zensical configuration, templates, styles, tags, and component rules |

Use [the reference coverage inventory](documentation-reference-coverage.md) for individual command,
configuration, format, Python, and runtime contracts.

## Decisions

- **Adopt** retains the source fact and may make the smallest wording or placement edit needed by
  the target page.
- **Rewrite** retains the subject but replaces wording, structure, or claims that do not match v2 or
  the accepted page type.
- **Split** assigns distinct source facts to their canonical procedure, concept, reference, or
  troubleshooting owners.
- **Reject** excludes the source block because it is stale, duplicated, proposed rather than
  implemented, or incompatible with the accepted site structure.

No decision permits copying a complete `more-docs` page without checking every command, field,
default, path, and claim against v2.

## Current v2 public pages

### Home and start material

| Source and section                                          | Target owner                                                                       | Decision | Reason and required treatment                                                                                                   | Evidence                  |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| `docs/index.md`: benchmark definition                       | `docs/index.md`                                                                    | Adopt    | Keep the definition, then route readers by goal.                                                                                | `DOC`                     |
| `docs/index.md`: site introduction and links                | `docs/index.md`                                                                    | Rewrite  | Distinguish the project website from documentation and provide the four accepted primary actions.                               | `DOC`, `SITE`             |
| `docs/get-started.md`: latest release acquisition           | `start-here/install-and-check.md`                                                  | Adopt    | Keep the release-first installation path and verify current release artefact names.                                             | `DOC`, `CLI`              |
| `docs/get-started.md`: checksum and ZIP extraction          | `start-here/install-and-check.md`                                                  | Adopt    | Keep integrity and extraction steps beside acquisition.                                                                         | `DOC`                     |
| `docs/get-started.md`: pinned releases and repository clone | `start-here/install-and-check.md`                                                  | Adopt    | Present tagged acquisition as an installation variant and state when generated release files differ from a checkout.            | `DOC`                     |
| `docs/get-started.md`: configuration-only setup             | `start-here/install-and-check.md`; `reference/cli/doctor.md`                       | Split    | Keep the procedure with installation. Put exact doctor flags and results in CLI reference.                                      | `DOC`, `CLI`              |
| `docs/get-started.md`: game prerequisite                    | `start-here/install-and-check.md`; `troubleshooting/game-and-displays.md`          | Adopt    | Keep the destructive or result-invalidating condition visible as a `danger` admonition. Link recovery by symptom.               | `DOC`, `RUNTIME`          |
| `docs/get-started.md`: Docker requirement                   | `start-here/install-and-check.md`                                                  | Adopt    | Restore the contextual infrastructure choice as a `question`. Do not move it to an FAQ.                                         | `DOC`, `SITE`             |
| `docs/get-started.md`: Redis setup and authentication       | `start-here/install-and-check.md`; `troubleshooting/redis-and-runtime-services.md` | Split    | Keep the required setup in the procedure and the network-exposure warning visible. Put symptom-led recovery in troubleshooting. | `DOC`, `RUNTIME`          |
| `docs/get-started.md`: OTLP collector and telemetry         | `start-here/install-and-check.md`; `reference/configuration/environment.md`        | Split    | Present telemetry as a setup choice. Put exact observability variables in reference.                                            | `DOC`, `CFG`              |
| `docs/get-started.md`: display setup                        | `start-here/install-and-check.md`; `troubleshooting/game-and-displays.md`          | Split    | Keep the platform requirement visible. Put failed-display diagnosis and recovery in troubleshooting.                            | `DOC`, `RUNTIME`          |
| `docs/get-started.md`: first dummy-player run               | `start-here/run-quickstart.md`                                                     | Adopt    | Make it the guided first run and add expected artefacts and verification.                                                       | `DOC`, `CLI`, `RESULT`    |
| `docs/get-started.md`: prior output artefacts               | Installation, result, and submission pages                                         | Split    | Keep the warning at each operation whose existing data changes behaviour. Preserve Parquet until validation finishes.           | `DOC`, `RESULT`, `SUBMIT` |

### Existing running pages

| Source and section                                          | Target owner                                                                    | Decision | Reason and required treatment                                                                                                       | Evidence                |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| `docs/running/index.md`                                     | `run-and-submit/index.md`                                                       | Rewrite  | Replace the thin directory listing with routes based on the reader's next task.                                                     | `DOC`, `SITE`           |
| `docs/running/add-new-player.md`: purpose and prerequisites | `run-and-submit/add-model.md`                                                   | Rewrite  | State the model-integration outcome and the configuration files the procedure creates.                                              | `DOC`, `CFG`            |
| Same page: scaffold commands and generated files            | `run-and-submit/add-model.md`; `reference/cli/model-configuration.md`           | Split    | Keep the ordered task in the procedure and exact command constraints in reference. Verify generated templates.                      | `CLI`, `CFG`            |
| Same page: profile naming                                   | `run-and-submit/add-model.md`; `reference/configuration/players.md`             | Rewrite  | Use the v2 player and provider naming constraints.                                                                                  | `CLI`, `CFG`            |
| Same page: identity                                         | `run-and-submit/add-model.md`; `understand/roles-protocols-and-capabilities.md` | Split    | Keep required identity fields in the task and explain identity, capability, and fingerprint relationships once in the concept page. | `CFG`, `RESULT`         |
| Same page: model class and provider                         | `run-and-submit/add-model.md`; `configure-provider.md`; configuration reference | Split    | Separate local player assembly from provider credentials and exact provider configuration.                                          | `CFG`                   |
| Same page: reasoning, safety, and model settings            | `run-and-submit/add-model.md`; player reference                                 | Rewrite  | Describe v2 configuration fields and validation. Remove provider-general claims that local code cannot establish.                   | `CFG`                   |
| Same page: capabilities                                     | Add-model procedure; roles and capabilities concept; player reference           | Split    | Record the configured values in the procedure, their effect in the concept, and exact fields in reference.                          | `CFG`, `SPEC`           |
| Same page: token measurement                                | `run-and-submit/add-model.md`; `reference/cli/model-configuration.md`           | Adopt    | Retain the calibration task and verify `measure-tokens-per-image` parameters.                                                       | `CLI`, `CFG`            |
| Same page: doctor validation                                | `run-and-submit/add-model.md`; `reference/cli/doctor.md`                        | Adopt    | Keep the verification step and link its exact modes to reference.                                                                   | `CLI`                   |
| `docs/running/run-your-model.md`: manifest fields           | `run-and-submit/create-run-manifest.md`; run-manifest reference                 | Split    | Keep a minimal complete procedure and render exact fields from v2 models.                                                           | `CFG`                   |
| Same page: identity and comparability                       | `understand/suites-revisions-and-comparability.md`; configuration reference     | Split    | Explain how suite, identity, capability, and digest choices affect comparison. Do not duplicate field tables.                       | `CFG`, `SPEC`, `RESULT` |
| Same page: validation                                       | `create-run-manifest.md`; `reference/cli/doctor.md`                             | Adopt    | Keep doctor before generation and execution.                                                                                        | `CLI`, `CFG`            |
| Same page: specification generation and suite selection     | `create-run-manifest.md`; generation, suite, and file reference                 | Split    | Keep the sequence in the procedure and exact contracts in grouped reference.                                                        | `CLI`, `SPEC`           |
| Same page: interactive play                                 | `run-and-submit/run-interactive.md`                                             | Adopt    | Preserve the run sequence after checking command names and resume behaviour.                                                        | `CLI`, `RUNTIME`        |
| Same page: result inspection                                | `run-and-submit/inspect-results.md`; result and file reference                  | Split    | Keep the reader task in the procedure and exact Parquet, outcome, and DuckDB contracts in reference.                                | `RESULT`                |
| Same page: static evaluation                                | `run-and-submit/run-statics.md`; static CLI and file reference                  | Rewrite  | Use the v2 `--player` vocabulary and current command set.                                                                           | `STATIC`                |

### Manuals and submission

| Source and section                                                  | Target owner                                                         | Decision | Reason and required treatment                                                                                     | Evidence                    |
| ------------------------------------------------------------------- | -------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------- | --------------------------- |
| `docs/manuals.md`: profile selection                                | `run-and-submit/prepare-manuals.md`; manuals configuration reference | Split    | Keep selection in the procedure and render profile fields in reference.                                           | `MANUAL`, `CFG`             |
| Same page: Chromium and compilation                                 | `prepare-manuals.md`; manual-preparation troubleshooting             | Split    | Keep required setup and commands in order. Put failed browser or compilation recovery under the observed symptom. | `MANUAL`, `CLI`             |
| Same page: cache and offline use                                    | `understand/manuals-and-rule-seeds.md`; manual files reference       | Split    | Explain content-addressed artefacts and cache boundaries once, then list the generated files in reference.        | `MANUAL`                    |
| Same page: repair and repeat operations                             | `troubleshooting/manual-preparation.md`; manuals CLI reference       | Split    | Put corrective commands beside symptoms and exact selection rules in CLI reference.                               | `MANUAL`, `CLI`             |
| Same page: authoring profiles                                       | `prepare-manuals.md`; manuals configuration reference                | Split    | Keep the authoring procedure distinct from the profile and source schemas.                                        | `MANUAL`, `CFG`             |
| `docs/submit-your-results.md`: introduction and four-stage workflow | `run-and-submit/submit-results.md`                                   | Adopt    | Retain the release-bound sequence: prepare inputs, build, validate, and submit.                                   | `SUBMIT`                    |
| Same page: prerequisites                                            | `submit-results.md`                                                  | Adopt    | Keep required suites, outputs, submitter data, repository access, and benchmark-integrity conditions visible.     | `SUBMIT`, `SPEC`, `RESULT`  |
| Same page: collate and retain outputs                               | `submit-results.md`; results concept                                 | Adopt    | Keep Parquet until the built bundle has passed validation.                                                        | `SUBMIT`, `RESULT`          |
| Same page: build bundle                                             | `submit-results.md`; submission CLI and file reference               | Split    | Keep the command sequence in the procedure. Put every option and bundle member in reference.                      | `SUBMIT`                    |
| Same page: local and remote validation                              | `submit-results.md`; submission troubleshooting                      | Split    | Keep required validation in the procedure. Put error categories and correction under symptoms.                    | `SUBMIT`                    |
| Same page: pull request submission                                  | `submit-results.md`                                                  | Adopt    | Keep the final repository workflow and dry-run path after checking current release instructions.                  | `SUBMIT`                    |
| `docs/includes/abbreviations.md`: project abbreviations             | Shared abbreviations include                                         | Adopt    | Keep abbreviations that improve tooltips across the site.                                                         | `DOC`, `SITE`               |
| Same file: domain definitions                                       | `reference/glossary.md`                                              | Split    | Put exact GPTNT terms in the glossary and link their first useful mention.                                        | `SITE`, all domain evidence |

## Committed `more-docs` changes

| Source                                      | Section or change                                                       | Target owner                               | Decision            | Reason                                                                                                                                            | Evidence                |
| ------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------ | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------- |
| `docs/index.md`                             | Full-page warning and installation framing                              | None                                       | Reject              | The home page must route by goal. Requirements belong on the installation page.                                                                   | `SITE`                  |
| Same page                                   | Benchmark definition and next actions                                   | `docs/index.md`                            | Rewrite             | Retain accurate definition text and use the four accepted actions.                                                                                | `DOC`, `SITE`           |
| `docs/get-started.md`                       | Preconditions, game, infrastructure, display, dummy run, and versioning | Start-here pages and troubleshooting       | Rewrite             | The content moves in a useful direction but the stronger v2 baseline and contextual admonitions control the result.                               | `DOC`, `CLI`, `RUNTIME` |
| `docs/running/index.md`                     | Alternate running index                                                 | None                                       | Reject              | It duplicates the accepted run-and-submit index without adding a distinct reader route.                                                           | `SITE`                  |
| `docs/running/add-new-player.md`            | Reorganised model setup                                                 | Slice B procedure, concepts, and reference | Split               | Retain useful task fragments only after checking templates, fields, and providers against v2.                                                     | `CLI`, `CFG`            |
| `docs/running/run-your-model.md`            | Reorganised execution flow                                              | Slice B and C pages                        | Split               | Retain useful ordering. Replace stale identity, manual, result, and command claims.                                                               | `CLI`, `CFG`, `RESULT`  |
| `docs/submit-your-results.md`               | Alternate submission workflow                                           | None                                       | Reject              | The v2 release-bound page and current bundle implementation have priority.                                                                        | `SUBMIT`                |
| `docs/concepts/index.md`                    | Concept directory                                                       | `understand/index.md`                      | Rewrite             | Route readers by relationship or decision rather than listing files.                                                                              | `SITE`                  |
| `docs/concepts/experiment-hierarchy.md`     | Hierarchy explanation                                                   | `understand/experiment-hierarchy.md`       | Rewrite             | Replace the incorrect hierarchy and absent `ExperimentDescriptor` with `ExperimentInstance`. Include suite digest, manual profile, and rule seed. | `SPEC`, `MANUAL`        |
| `docs/concepts/experiment-specification.md` | Field catalogue                                                         | Experiment-specification reference         | Rewrite             | Group fields by domain and generate exact v2 schema details.                                                                                      | `SPEC`                  |
| Pairing abbreviations                       | `other`, `self-play`, and related terms                                 | None                                       | Reject              | The current values are `pairwise`, `with_self`, `no_expert`, and `with_best_*`.                                                                   | `SPEC`                  |
| Repository header link                      | Header repository action                                                | Shared site foundation                     | Adopt               | Retain if it fits the accepted navigation and passes layout checks.                                                                               | `SITE`                  |
| `griffe-pydantic` dependency                | Pydantic field rendering                                                | Shared API foundation                      | Adopt conditionally | Add it only after one grouped schema page proves that the dependency supplies required rendering.                                                 | `CFG`, `SITE`           |
| `extra.css` changes                         | API and heading presentation                                            | Shared styles                              | Rewrite             | Retain only rules supported by visual checks. Do not apply global wrapping or element-hiding rules.                                               | `SITE`                  |
| Python docstrings                           | `PairingType`, `Modality`, `Role`, and `CommunicationStyle`             | Current v2 source objects                  | Adopt conditionally | Retain accurate descriptions after a wording check and a separate source-docstring assignment.                                                    | `SPEC`, `CFG`           |
| Python docstrings                           | `ExperimentSpec` fields                                                 | Current v2 `ExperimentSpec`                | Rewrite             | Describe current fields, invariants, and provenance inputs. Do not retain removed or renamed fields.                                              | `SPEC`                  |
| Zensical design changes                     | Navigation and feature configuration                                    | Shared site foundation                     | Split               | Assess each feature independently under the accepted Zensical conventions.                                                                        | `SITE`                  |
| Heading-spacing change                      | Theme override                                                          | Shared styles                              | Adopt conditionally | Keep only if rendered pages demonstrate that the theme spacing needs correction.                                                                  | `SITE`                  |
| Ignore-file change                          | Generated site artefacts                                                | Repository configuration                   | Reject by default   | Add an ignore entry only when the new worktree produces the same artefact.                                                                        | `SITE`                  |

## Uncommitted `more-docs` working-tree material

### Landing, guided, concept, and procedure pages

| Source and section                                                   | Target owner                                       | Decision | Reason and required treatment                                                                                          | Evidence                   |
| -------------------------------------------------------------------- | -------------------------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| `docs/index.md`: rewritten home                                      | `docs/index.md`                                    | Rewrite  | Retain accepted reader routes, but apply the approved home-page action order and v2 definition.                        | `DOC`, `SITE`              |
| `docs/get-started.md`: rewritten setup                               | `start-here/install-and-check.md`                  | Rewrite  | Use v2 as the baseline and restore contextual questions, warnings, and danger blocks to their subjects.                | `DOC`, `CLI`, `RUNTIME`    |
| `docs/tutorial/run-the-benchmark.md`: introduction and prerequisites | `start-here/run-quickstart.md`                     | Adopt    | Retain the outcome-led opening where it agrees with v2.                                                                | `CLI`, `CFG`               |
| Same page: command sequence and expected output                      | Quickstart, choose-next-workflow, and reference    | Split    | Verify every command, deterministic input, output path, and success condition. Do not retain a separate Tutorial area. | `CLI`, `RESULT`, `SITE`    |
| `docs/guides/index.md`                                               | `understand/index.md`                              | Rewrite  | Replace the Guides label with relationship-based concept routing.                                                      | `SITE`                     |
| Comparability guide: version-only comparability                      | None                                               | Reject   | Version alone does not describe suite, identity, capability, configuration, dataset, or provenance compatibility.      | `SPEC`, `RESULT`, `STATIC` |
| Comparability guide: remaining revision and provenance material      | `understand/suites-revisions-and-comparability.md` | Rewrite  | Use current suite locks, digests, protected state, and static dataset revisions.                                       | `SPEC`, `RESULT`, `STATIC` |
| Hierarchy guide                                                      | `understand/experiment-hierarchy.md`               | Rewrite  | Use `ExperimentInstance`, not `ExperimentDescriptor`, and connect hierarchy to specifications and attempts.            | `SPEC`                     |
| Runtime guide                                                        | Runtime concept and contributor runtime reference  | Split    | Keep relationships in the concept. Put exact services, channels, and payloads in reference.                            | `RUNTIME`                  |
| Results guide                                                        | Results concept and file reference                 | Split    | Correct the distinction among player record, record footer, experiment outcome, summary, and database row.             | `RESULT`                   |
| `docs/how-to/index.md`                                               | `run-and-submit/index.md`                          | Rewrite  | Replace the How-to label with task routes in execution order.                                                          | `SITE`                     |
| Add-player how-to                                                    | `run-and-submit/add-model.md`                      | Split    | Verify generated templates and distribute provider, capability, and API detail to their owners.                        | `CLI`, `CFG`               |
| Provider how-to                                                      | `configure-provider.md`; provider reference        | Split    | Verify local configuration and environment variables. Keep the credential warning visible.                             | `CFG`                      |
| Run-manifest how-to                                                  | `create-run-manifest.md`; manifest reference       | Split    | Keep one complete canonical example and generate exact field detail.                                                   | `CFG`                      |
| Interactive-run how-to                                               | `run-interactive.md`; CLI and runtime reference    | Split    | State that `run` does not generate specifications. State that `--force` does not bypass benchmark-integrity checks.    | `CLI`, `RUNTIME`           |
| Statics how-to                                                       | `run-statics.md`; static CLI and file reference    | Split    | Retain the current command inventory. Verify shared and task-specific options and every output path.                   | `STATIC`                   |
| `docs/submit-results/*`                                              | Current v2 submission procedure and reference      | Reject   | The working-tree hierarchy and claims conflict with the current release workflow. Rebuild from v2 evidence.            | `SUBMIT`                   |

### FAQ content restoration

| FAQ heading                            | Canonical owner                                           | Decision and required component                                                         | Evidence           |
| -------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------ |
| Whether Docker is required             | `start-here/install-and-check.md`                         | Adopt as a visible `question` beside infrastructure setup.                              | `DOC`, `SITE`      |
| Default Redis authentication           | Installation and Redis troubleshooting                    | Split setup from recovery. Preserve the network-exposure `warning`.                     | `RUNTIME`, `SITE`  |
| Running without exported telemetry     | Installation and environment reference                    | Split choice from variables. Use linked alternatives only when both paths are verified. | `CFG`, `SITE`      |
| Whether `mise` is required             | Installation variants                                     | Adopt as linked `mise` and direct-`uv` tabs only after both sequences pass.             | `CLI`, `SITE`      |
| Removing Parquet after DuckDB creation | Results concept, file reference, and submission procedure | Split. Preserve the visible warning through successful submission validation.           | `RESULT`, `SUBMIT` |
| What `gptnt run` starts                | Interactive procedure, runtime concept, and CLI reference | Split the task effect, service relationship, and exact command contract.                | `CLI`, `RUNTIME`   |

Remove the FAQ only after these six rows are implemented on their canonical pages. Do not preserve an
FAQ copy after restoration.

### Reference drafts, stubs, and examples

| Source and section                            | Target owner                         | Decision              | Reason and required treatment                                                                           | Evidence            |
| --------------------------------------------- | ------------------------------------ | --------------------- | ------------------------------------------------------------------------------------------------------- | ------------------- |
| `docs/reference/index.md`                     | `reference/index.md`                 | Rewrite               | Route by CLI, configuration, files, Python API, runtime implementation, and glossary.                   | `SITE`              |
| Glossary: hierarchy terms                     | `reference/glossary.md`              | Rewrite               | Define current suite, specification, attempt, instance, session, record, and outcome terms.             | `SPEC`, `RESULT`    |
| Glossary: player and communication terms      | `reference/glossary.md`              | Rewrite               | Define player, model, provider, role, protocol, capability, identity, and fingerprint distinctions.     | `CFG`, `SPEC`       |
| Glossary: manual terms                        | `reference/glossary.md`              | Rewrite               | Define profile, source, artefact, mission, key, and rule seed from current models.                      | `MANUAL`, `SPEC`    |
| Glossary: result and provenance terms         | `reference/glossary.md`              | Rewrite               | Define Parquet record, footer, outcome, summary, DuckDB, provenance, and protected state.               | `RESULT`            |
| Glossary: statics and submission terms        | `reference/glossary.md`              | Rewrite               | Define static task, dataset revision, bundle, target, and validation.                                   | `STATIC`, `SUBMIT`  |
| Run-manifest class-per-page stubs             | Grouped configuration and file pages | Split                 | Consolidate `RunManifest`, `Anchors`, `PlayerSpec`, and `Source` under domain headings.                 | `CFG`               |
| Experiment-specification class-per-page stubs | Grouped specification page           | Split                 | Consolidate current specification, pairing, suite, mission, and generation contracts by domain.         | `SPEC`              |
| `ExperimentDescriptor` stub                   | None                                 | Reject                | No such current v2 model exists. Use `ExperimentInstance` where the runtime instance is meant.          | `SPEC`, `RUNTIME`   |
| Runtime class-per-page stubs                  | Grouped runtime subsystem pages      | Split                 | Group orchestration, experiment manager, registry, heartbeat, game, player, RPC, and recording objects. | `RUNTIME`, `RESULT` |
| Example experiment JSON                       | Specification example                | Reject and regenerate | Generate a valid v2 example from the current schema or repository quickstart.                           | `SPEC`              |
| API templates                                 | Shared API foundation                | Adopt conditionally   | Retain only overrides required by the grouped schema and extension-page render proofs.                  | `SITE`              |

### Site configuration, styles, source prose, and design notes

| Source                                                                    | Target owner                                            | Decision              | Reason and required treatment                                                                                 | Evidence            |
| ------------------------------------------------------------------------- | ------------------------------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------- |
| `zensical.toml`: Tutorial, FAQ, Guides, How-to, and class-page navigation | None                                                    | Reject                | Use the accepted goal-led tabs and grouped reference.                                                         | `SITE`              |
| `zensical.toml`: content features                                         | Shared site foundation                                  | Split                 | Enable only features listed in the specification and verify their use. Do not enable navigation expansion.    | `SITE`              |
| API stylesheet changes                                                    | Shared styles                                           | Rewrite               | Test grouped rendering in both colour schemes and on mobile. Remove global wrapping or arbitrary hiding.      | `SITE`              |
| `RunManifest` and `PlayerSpec` docstrings                                 | Current v2 objects                                      | Adopt with correction | Retain only descriptions that state an input source, constraint, or relationship not apparent from the field. | `CFG`               |
| Leaderboard suite reduction in Python                                     | None                                                    | Reject                | It is an unrelated behaviour change and cannot enter the documentation migration.                             | `SPEC`, `SUBMIT`    |
| `docs/design/manual-system.md`: implemented manual lifecycle              | Manual concept, procedure, files, and runtime reference | Split and rewrite     | Extract current profile, source, resolution, artefact, cache, and injection behaviour after checking v2.      | `MANUAL`, `RUNTIME` |
| Same design: proposed Rule Seed Modifier                                  | None                                                    | Reject                | It describes a proposal, not current v2 behaviour.                                                            | `MANUAL`, `SPEC`    |
| Same design: proposed community-manual bridge                             | None                                                    | Reject                | It describes a future integration without a current interface.                                                | `MANUAL`            |
| Same design: stages, delivery plan, and proposed tests                    | None                                                    | Reject                | Internal planning does not belong in public product documentation.                                            | `MANUAL`, `SITE`    |
| `.config/wt`, `.DS_Store`, and unrelated working-tree files               | None                                                    | Reject                | They have no documentation destination.                                                                       | `SITE`              |

## Canonical subject ownership

| Subject                              | Canonical owner                                    | Other pages may contain                                |
| ------------------------------------ | -------------------------------------------------- | ------------------------------------------------------ |
| Acquisition and prerequisites        | `start-here/install-and-check.md`                  | A short prerequisite and a link                        |
| First complete run                   | `start-here/run-quickstart.md`                     | A next action or reference anchor                      |
| Model integration                    | `run-and-submit/add-model.md`                      | Exact fields and concepts by link                      |
| Provider setup                       | `run-and-submit/configure-provider.md`             | Provider fields and external documentation links       |
| Manual preparation                   | `run-and-submit/prepare-manuals.md`                | Manual concepts, fields, formats, and recovery by link |
| Run-manifest authoring               | `run-and-submit/create-run-manifest.md`            | Exact schema fields by link                            |
| Experiment hierarchy                 | `understand/experiment-hierarchy.md`               | Exact object definitions by link                       |
| Roles, protocols, and capabilities   | `understand/roles-protocols-and-capabilities.md`   | Exact values and fields by link                        |
| Suites and comparability             | `understand/suites-revisions-and-comparability.md` | Suite and lock schemas by link                         |
| Runtime relationships                | `understand/runtime-services.md`                   | Subsystem contracts in contributor reference           |
| Results and provenance               | `understand/results-and-provenance.md`             | Format and command details by link                     |
| Static execution                     | `run-and-submit/run-statics.md`                    | Exact commands and output schemas by link              |
| Submission workflow                  | Current v2 `run-and-submit/submit-results.md`      | CLI, bundle, and validation detail by link             |
| Exact project definitions            | `reference/glossary.md`                            | Linked first mentions                                  |
| Fields, options, values, and formats | Grouped reference pages                            | Task-specific excerpts only                            |
| Failure and recovery                 | Symptom-led troubleshooting page                   | Visible requirement or warning where it first applies  |

## Required reference baseline

The public reference must include these grouped domains. The coverage inventory expands each group
into verified interfaces and explicit exclusions.

- CLI: command overview, doctor, generate, run, results and analysis, statics, submission, and
  maintenance commands.
- Configuration: run manifest, player, provider, suite, missions, manuals, and environment
  variables.
- Files and schemas: experiment specifications and outcomes, player records, DuckDB,
  static outputs, submission bundles, and output layout.
- Python API: player interfaces, actions and observations, processors, experiment generation, and
  supported extension points.
- Runtime implementation pages cover the experiment manager and service registry. They also cover
  game and player services, heartbeats, and RPC.
- Glossary: exact GPTNT terms used across every layer.

This baseline is explicit in the plan. It is not replaced by the narrower Python API inventory.

## Conflicts and implementation gates

Resolve these items before the affected public page is accepted:

1. Use `configs/player`, not the `configs/model` path found in candidate prose.
2. Use `ExperimentInstance`, not the absent `ExperimentDescriptor` type.
3. Describe current provenance fields and protected-benchmark state. Do not use the candidate
   `ProvenanceMixin` or `git_sha` schema as a stored-object description.
4. Define suite comparability through the current configuration and suite digests, lock entries,
   identities, capabilities, and revisions. A version string alone is insufficient.
5. Check the required interactive suites and static targets against the current submission schema
   and release workflow. Candidate submission pages disagree with both.
6. State that a submission bundle contains the reduced `suites.lock` where applicable.
7. Keep player-record Parquet until submission validation succeeds.
8. Describe only the current manual profile, source, artefact, cache, and rule-seed behaviour.
   Exclude proposed manual-system features.
9. Group generated Python and runtime objects by reader domain. Do not restore class-per-page
   navigation.
10. Use the v2 pairing values and static `--player` option. Do not retain candidate synonyms as
    command or configuration values.

## Completion check

The migration is closed only when every row is implemented on its target page with evidence
recorded or has an accepted rejection, every restored admonition remains on its subject page, and
no public page relies on `more-docs` as behavioural evidence.
