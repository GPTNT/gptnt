# Documentation site specification

- Status: draft for approval
- Applies to: GPTNT v2 and later
- Implementation branch: `codex/docs-site`
- Migration base: `origin/v2` at `527fdeab`
- Migration source: `more-docs` at `8753f455` and its documentation working tree on 23 August 2026

## Purpose

A documentation site specification is a tracked project design document. It records how the GPTNT
site is organised, written, generated, migrated, and checked. It is not rendered as part of the
public site.

This file records the accepted documentation decisions and the remaining implementation work.
Change this file before implementing a conflicting site structure, page convention, reference
policy, or prose rule. Record completed migration work in the checklists instead of maintaining a
separate plan.

The documentation work takes place in one worktree based on `origin/v2`. The `more-docs` branch is
an earlier attempt that contains candidate prose, structure, styles, and reference experiments. It
has no authority over the new site. Do not continue site work on `more-docs`, merge it wholesale,
or presume that any of its decisions should survive.

## Objectives

The site must let a reader:

1. Install GPTNT and check that the machine can run it.
2. Complete a benchmark run with the included players.
3. Add and configure a model.
4. Run interactive experiments and static evaluations.
5. Inspect, analyse, and submit results.
6. Understand the experiment, runtime, identity, manual, and result models.
7. Find exact commands, configuration fields, formats, and supported Python interfaces.
8. Reach implementation detail progressively when maintaining or extending GPTNT.

The site describes v2 and later. It does not preserve pre-v2 instructions or provide a migration
guide from the pre-v2 system.

The site does not collect analytics or show an analytics-backed page-feedback control.

## Audiences and order of presentation

The site serves these readers in this order:

1. A person evaluating or running the benchmark.
2. A person integrating a model.
3. A person preparing and submitting results.
4. A person contributing to GPTNT.

This order controls landing pages and default navigation, not content availability. Contributor
reference remains in the same site and appears through deeper navigation, cross-references, search,
and tags. Do not isolate it in a separate site or conceal it behind an unexplained "internals"
label.

## Information architecture

Use reader goals for top-level navigation and domain names for deeper reference navigation.

```text
Home

Start here
  Install and check GPTNT
  Run the quickstart
  Choose the next workflow

Run and submit
  Add a model
  Configure a provider
  Prepare manuals
  Create a run manifest
  Run interactive experiments
  Run static evaluations
  Inspect and analyse results
  Submit results

Understand GPTNT
  Benchmark and player model
  Experiment hierarchy
  Roles, protocols, and capabilities
  Suites, revisions, and comparability
  Runtime services
  Results and provenance
  Manuals and rule seeds

Reference
  CLI
  Configuration
  Files and schemas
  Python API
  Runtime implementation
  Glossary

Troubleshooting
  Installation and doctor
  Game and displays
  Redis and runtime services
  Providers and model responses
  Interrupted runs and outputs
  Submission validation
```

Use these paths:

```text
docs/
  index.md
  start-here/
  run-and-submit/
  understand/
  reference/
    cli/
    configuration/
    files/
    python/
    runtime/
  troubleshooting/
```

The visible label and URL do not have to use the same wording. Paths follow their top-level journey
folder. This implementation replaces the legacy root-level and `running/` paths without redirects
because the reader-journey structure controls the published layout. Update every inbound reference
in the same change. Preserve URLs after this alignment unless another approved structure change
requires a move.

### Home

The home page states what GPTNT measures and distinguishes the project website from the
documentation. It presents the five top-level reader journeys in a concise Zensical card grid. Each
card links to its section overview, and cards may include direct task links when that route has a
common entry or completion point. Keep install, quickstart, model integration, and submission
reachable from the grid without listing the complete site map. Do not apply button classes to card
links.

### Start here

`Start here` is one guided sequence, not a separate "Get started" page followed by an unrelated
"Tutorial" section.

`Install and check GPTNT` covers acquisition, prerequisites, KTANE, display requirements,
dependencies, Redis, observability, and `gptnt doctor`.

`Run the quickstart` uses the included players to generate experiment specifications, run KTANE,
write records, build the database, and inspect the result. It states what the reader produces at
each step and how to confirm success.

`Choose the next workflow` routes the reader to model integration, interactive runs, statics,
analysis, submission, or concepts.

### Run and submit

This section contains task-oriented procedures. A page starts with the goal and prerequisites,
then presents an ordered procedure, verification, and relevant failure recovery. It links to exact
reference fields rather than reproducing their complete definitions.

Submission is the final stage of a benchmark workflow, so it belongs in this section. It remains a
prominent home-page action.

### Understand GPTNT

This section explains why boundaries exist and how decisions affect adjacent components. Put a
sequence of unrelated definitions in reference material.

Use diagrams for relationships among levels, transitions between states, service call order,
ownership boundaries, or data flow. Do not add a diagram that repeats a short paragraph.

### Reference

Reference pages answer exact questions about accepted inputs, generated outputs, fields, defaults,
commands, values, and callable interfaces. Put workflows from beginning to end in `Start here` or
`Run and submit`.

Reference is broader than the Python API. CLI commands, configuration files, persisted formats, and
service contracts are interfaces even when a reader never imports Python.

### Troubleshooting

Troubleshooting pages begin with an observed symptom. Each entry identifies the likely condition,
the check that distinguishes it, and the corrective action. Put the explanation of the underlying
system in `Understand GPTNT` and link to it.

There is no top-level FAQ. A question with a canonical subject belongs on that subject's page.

## Page types

Every public page has one primary type and may link to another type. Keep a complete tutorial
separate from a concept explanation or object catalogue.

### Landing page

A landing page contains:

1. One paragraph defining the section.
2. A small set of primary next actions.
3. A table or short list routing readers by goal.
4. Links to adjacent sections when a reader may have arrived at the wrong level.

### Guided page

A guided page presents one complete path in a controlled order. It contains:

1. The outcome.
2. Prerequisites.
3. Ordered steps.
4. Expected intermediate state where it prevents uncertainty.
5. A verification step.
6. Next workflows.

The quickstart is the main guided path. Do not add several competing first-run tutorials.

### Procedure

A procedure solves one task for a reader who already understands the surrounding system. Use an
imperative title and ordered steps. Separate required steps from optional variants through tabs or
collapsible blocks.

### Concept page

A concept page explains relationships, boundaries, and consequences. Introduce only the terms
needed for the explanation. Link each exact field or allowed value to reference material.

### Reference page

A reference page starts with a short statement of scope. It then presents exact fields, commands,
formats, values, or callable objects. Group related objects by domain instead of creating a sidebar
entry for every class.

### Troubleshooting page

A troubleshooting page groups symptoms by the operation in which they appear. Use `failure`,
`bug`, `warning`, or `question` admonitions when the block's meaning matches that type. Do not use
an admonition as a substitute for the corrective procedure.

## Progressive exposure

Progressive exposure controls presentation depth while keeping all material available.

1. The home page offers goals.
2. Section indexes offer tasks or domains.
3. Overview pages explain relationships.
4. Reference sections provide exact contracts.
5. Generated Python and runtime details appear at the deepest level.

Use section indexes, collapsed navigation groups, cross-references, search, tags, and optional
details blocks to support this sequence. Do not enable navigation expansion by default. Do not use
an audience label to make contributor reference appear unrelated to the rest of GPTNT.

Every deep reference page must link to its domain overview. A domain overview links to at least one
procedure or concept page when either exists.

## Reference and API integration

### Reference layers

| Layer                  | Reader question                                            | Primary evidence                                    | Presentation                                                           |
| ---------------------- | ---------------------------------------------------------- | --------------------------------------------------- | ---------------------------------------------------------------------- |
| CLI                    | Which command and option performs this operation?          | Cyclopts command registrations and parameters       | Hand-written command grouping with generated or verified option detail |
| Configuration          | Which keys, types, defaults, and constraints are accepted? | Pydantic models, Hydra configuration, and templates | Hand-written overview followed by generated model fields               |
| Files and schemas      | What does GPTNT read or write?                             | Serialised models, DuckDB schema, and output paths  | Format overview, field tables or generated models, and valid examples  |
| Python API             | What may an integration import and call?                   | Selected public classes, protocols, and functions   | Curated domain pages rendered with `mkdocstrings`                      |
| Runtime implementation | Which components implement a run?                          | Service contracts and implementation types          | Subsystem overviews with selected generated objects                    |

### Hand-written and generated content

Use hand-written prose for:

- Purpose and scope.
- Relationships among objects.
- Stability and compatibility expectations.
- Complete examples.
- Operational constraints.
- Links to procedures and concepts.

Use generated API output for:

- Field names, types, defaults, and descriptions.
- Function and method signatures.
- Enumerated values.
- Return types and declared exceptions.
- Cross-references among Python objects.

Do not copy a generated field table into prose. Do not expect generated output to explain why the
reader uses the object.

### Supported Python surface

Maintain an explicit allowlist of supported Python integration points. Include an object when at
least one condition applies:

- A custom player, provider, processor, or action is expected to use it.
- A user is expected to instantiate or implement it.
- A configuration or persisted format exposes it.
- Another package is expected to import it.
- Compatibility across versions is part of its contract.

Do not publish the package tree automatically. Private helpers and incidental runtime classes do
not become supported interfaces because `mkdocstrings` can render them.

Runtime implementation types remain available when contributors need them to trace experiments or
maintain services. Include protocol objects needed to explain those operations. Their overview must
state that they describe the current implementation rather than a supported extension point.

### Source layout and reference inclusion

Module privacy and supported-reference inclusion are separate decisions. A private module may
contain an object selected for maintainer reference, while a public module does not make every
object inside it a supported interface.

The initial source-layout audit renamed these implementation-only modules:

- `common._run_once`
- `interactive.services._exceptions`
- `interactive.services.registry._metrics`
- `cli.player._templates`
- `cli.manual._selection`
- `cli.run._monitor`
- `cli.run._pipeline`

Broader dashboard, runtime, and cross-CLI renames were deliberately deferred until their ownership
and import contracts can be assessed as separate changes.

### Page grouping

Render related objects on a domain page unless one object requires enough explanation to justify a
separate page. For example, a run-manifest page may render `RunManifest`, `PlayerSpec`, `Anchors`,
and `Source` under separate headings.

Use per-directive `mkdocstrings` options where user-facing schemas and developer-facing Python
objects need different output:

- User-facing schema pages show fields, types, defaults, descriptions, and cross-references. Hide
  inherited Pydantic machinery and source blocks.
- Python extension pages show callable signatures, public methods, exceptions, and source links
  when a source link helps an implementer.
- Runtime pages show only members discussed by the subsystem overview or needed to trace the
  contract.

The navigation label uses the domain term. Python paths appear in headings, generated signatures,
and cross-references rather than replacing the domain label.

### Coverage inventory

Use the [reference field documentation inventory](documentation-reference-field-inventory.md) as
the implementation-backed backlog for field descriptions and object-level explanations. It is a
planning input rather than public documentation.

Use the [reference coverage inventory](documentation-reference-coverage.md) as the checked v2 map
of commands, configuration, persisted formats, supported Python interfaces, and contributor-only
runtime contracts. It records evidence, proposed page ownership, presentation mode, cross-links,
and explicit exclusions.

Maintain a checked inventory for:

- Every top-level CLI command and nested subcommand.
- Every user-editable configuration model.
- Every persisted input and output format.
- Every supported Python extension point.
- Every runtime subsystem included in contributor reference.

Adding one of these interfaces requires either a reference entry or an explicit exclusion with a
reason. Prefer deriving checks from command registrations and selected models over maintaining a
second handwritten list of fields.

Use this as the initial reference coverage map. Verify every entry against `v2`, add omitted
interfaces found during the inventory, and record an explicit exclusion when an entry does not
warrant its own page or generated section.

```text
CLI
  Command overview
  doctor
  generate
  run
  results and analysis
  statics
  submission
  maintenance commands

Configuration
  Run manifest
  Player configuration
  Provider configuration
  Suite configuration
  Missions
  Manuals
  Environment variables

Files and schemas
  Experiment specifications
  Player records
  Experiment outcomes
  DuckDB database
  Static evaluation outputs
  Submission bundles
  Output directory layout

Python API
  Player interfaces
  Actions and observations
  Processors
  Experiment generation
  Supported extension points

Runtime implementation
  Experiment manager
  Game service
  Player service
  Service registry
  Heartbeats and RPC
```

## Zensical conventions

Use Zensical components where they identify structure, alternatives, state, or supporting detail.
Do not add components only to vary the appearance of a page.

### Navigation features

The intended navigation configuration uses:

- `navigation.tabs` and `navigation.tabs.sticky` for top-level areas.
- `navigation.sections` for groups within a selected tab.
- `navigation.indexes` for section overview pages.
- `navigation.path` for breadcrumbs.
- `navigation.instant`, `navigation.instant.prefetch`, and `navigation.instant.progress`.
- `navigation.footer`, `navigation.top`, and `navigation.tracking`.
- `toc.follow` and `search.highlight`.

Do not enable `navigation.expand`. Collapsed groups provide progressive exposure. Do not enable
`toc.integrate` because it conflicts with section indexes. Add `navigation.prune` only if measured
site size or rendering time requires it and after verifying that deep reference remains easy to
reach.

### Admonitions

Use the complete admonition vocabulary according to meaning:

| Type       | Use                                                                                           |
| ---------- | --------------------------------------------------------------------------------------------- |
| `abstract` | Summarise a page, generated artifact, or multi-stage operation.                               |
| `info`     | Supply contextual information needed to interpret the surrounding section.                    |
| `note`     | State an operational detail or qualification.                                                 |
| `tip`      | Offer an optional convenience or shorter path.                                                |
| `success`  | State an expected verification result.                                                        |
| `question` | Present a choice or answer a likely question at the point it arises.                          |
| `warning`  | Identify a platform limitation, comparability risk, or consequential caveat.                  |
| `failure`  | Describe an expected failure state and its correction.                                        |
| `danger`   | Mark a requirement or action that can invalidate results or damage data.                      |
| `bug`      | Document a confirmed defect or platform problem and its workaround.                           |
| `example`  | Hold a complete worked configuration, command sequence, or output.                            |
| `quote`    | Attribute a short external definition when paraphrasing would remove a necessary distinction. |

Choose `!!!` for information that should remain visible. Choose `???` for optional depth and
`???+` when optional content should initially be open. Keep requirements visible.

Restore contextual admonitions from `origin/v2` and `more-docs` to their subject pages. Do not move
Docker alternatives, telemetry choices, storage constraints, or runtime explanations into an FAQ.

### Content tabs

Use linked tabs for mutually exclusive variants that perform the same task, including:

- Linux, macOS, and Windows.
- `mise` and direct `uv` usage.
- Hosted and self-hosted providers.
- Defuser and Expert examples.
- Closed and open model configuration when the fields differ.

Use the same tab label everywhere so `content.tabs.link` preserves the reader's selection. Do not
put sequential steps into tabs.

### Code blocks and annotations

Enable code copy, code selection, annotations, and line anchors. Use annotations to explain a line
whose meaning depends on GPTNT. Do not annotate syntax already apparent from YAML, TOML, JSON, or
shell notation.

Every command block states where it runs when the location is not the repository root. Use valid
examples that match v2. Show expected output when it is the verification step or when a successful
command otherwise appears idle.

Use a titled `bash` fence for commands that the reader can copy into a shell. Omit the `$` prompt so
the block remains copyable. Use `console title="Shell session"` only when a transcript combines
commands and their output, and prefix commands in that transcript with `$`. Use
`text title="Expected output"` for output without commands. Prefer a short task-specific title such
as `Install dependencies`, `Start services`, or `Validate the player` to the generic
`Run in your shell` title.

Test titled language fences before adding a shell icon. Do not add a decorative icon or custom CSS
for command blocks unless the titled fences leave the distinction unclear in the rendered site.

### Tooltips, glossary, and footnotes

Keep project-wide abbreviations in `docs/includes/abbreviations.md` and enable improved tooltips.
Use the glossary for domain definitions and link to the canonical entry from concepts and
reference.

Use footnote tooltips for supporting qualifications that are relevant but would interrupt the
procedure. Do not put requirements or error recovery only in a footnote.

### Diagrams

Use Mermaid flowcharts for workflows and ownership, sequence diagrams for service calls, state
diagrams for lifecycle, and class diagrams only when type relationships matter to the reader.

Prefer Zensical's Mermaid integration. Retain the existing `beautiful-mermaid` enhancement only if
it works with instant navigation, both colour schemes, keyboard navigation, reduced motion, and a
plain Mermaid fallback. Record the renderer choice in this file when the site foundation is
implemented.

### Images

Use captions, lazy loading, colour-scheme variants, and GLightbox where a screenshot or rendered
artifact adds information. Give every image descriptive alternative text. Do not use a screenshot
as the only record of a command, field, or error message.

### Links and previews

Use ordinary Markdown links, compact route lists, or direct next-step prose. Do not apply button
classes to navigation links. Use instant previews on links where a reader benefits from checking a
definition without leaving a procedure.

### Tags

Tags provide search and lateral discovery. They do not replace navigation. Apply one to three tags
to a page from this controlled vocabulary:

- `Configuration`
- `CLI`
- `Model integration`
- `Extension API`
- `Runtime`
- `Results`
- `Submission`
- `Maintainer reference`

Add a tag only when it helps a reader find related material outside the page's navigation section.
Do not create synonyms or tags that repeat the page type. Revisit the vocabulary if Zensical adds
tag listing pages that change how readers use tags.

Assign each controlled tag a stable identifier and a bundled icon. Use page icons on section
indexes or reference groups when the icon communicates the subject. Do not add icons or emoji only
as decoration.

### Features not used

Do not configure analytics, cookie consent, or analytics-backed page feedback. Do not add a version
selector for pre-v2 documentation. Design URLs so v2 and later can be deployed through versioned
documentation when more than one maintained version needs to remain available.

### Zensical implementation references

Use the current official Zensical documentation when implementing these conventions:

- [Navigation](https://zensical.org/docs/setup/navigation/)
- [Admonitions](https://zensical.org/docs/authoring/admonitions/)
- [Content tabs](https://zensical.org/docs/authoring/content-tabs/)
- [Code blocks and annotations](https://zensical.org/docs/authoring/code-blocks/)
- [Tooltips and abbreviations](https://zensical.org/docs/authoring/tooltips/)
- [Footnotes](https://zensical.org/docs/authoring/footnotes/)
- [Diagrams](https://zensical.org/docs/authoring/diagrams/)
- [Images and lightboxes](https://zensical.org/docs/authoring/images/)
- [Tags](https://zensical.org/docs/setup/tags/)
- [Front matter and page icons](https://zensical.org/docs/authoring/frontmatter/)
- [Icons and emoji](https://zensical.org/docs/authoring/icons-emojis/)
- [Extension and `mkdocstrings` support](https://zensical.org/docs/setup/extensions/about/)
- [Versioned deployments](https://zensical.org/docs/setup/versioning/)

## Prose style

### Voice and structure

- Use direct, literal prose. State the operation, input, output, condition, or constraint.
- Describe current v2 behaviour. Use historical language only when compatibility or migration
  depends on the earlier state.
- Address the reader as "you" in guided pages and procedures. Use neutral descriptions in concepts
  and reference. Use "we" only for a project policy or action performed by project maintainers.
- Put the outcome before background on task pages.
- Explain stateful operations in execution order: input, operation, state change, invariant, then
  relevant failure.
- Use separate sentences for separate facts and ordinary punctuation.
- Use one canonical explanation for each topic and link to it elsewhere.
- Preserve an existing informal register when it communicates the mechanism. Do not replace it with
  formal or corporate wording only to make pages sound uniform.
- Make the smallest sufficient edit when a v2 passage keeps the same purpose and location. The
  accepted information architecture may still require a page to move, split, or change type. The
  minimal-edit rule does not give `more-docs` wording or structure a presumption of retention.
- Use British English in prose. Preserve code identifiers, command output, and external product
  terminology exactly.
- Wrap Markdown prose at 100 columns where tables, links, and generated syntax permit.

### Terminology

Use one term for one concept. Define a project term before relying on it. Maintain the distinctions
among run manifest, suite, mission, experiment specification, attempt, session, player record,
experiment outcome, and submission bundle.

Refer to code by command, field, function, class, or module name. Do not use source line numbers in
public documentation. Link to official external documentation for provider model lists and setup
instructions maintained outside GPTNT.

### Headings and links

Use imperative headings for procedures and noun headings for concepts and reference. A heading
must describe the content below it. Avoid headings such as "Overview" when a specific subject fits.

Link the first useful mention of a related GPTNT topic. Do not link every repeated term. Use
descriptive link text rather than "here". Check every fragment after headings move.

### Examples

An example must be valid for the documented v2 interface. Prefer repository templates and
quickstart configuration over invented structures. State what the reader may change and which
values must remain consistent.

Keep one complete canonical example for a format when possible. Use shorter excerpts elsewhere and
link to the complete example.

## Evidence and accuracy

Use these sources in order:

1. Accepted behaviour and decisions in the current task.
2. CLI registrations, Pydantic models, configuration composition, serialised models, and tests on
   the v2 branch.
3. Included templates, quickstart files, and release workflow.
4. Existing documentation that agrees with the implementation.
5. Official external project or provider documentation.

`more-docs` is not evidence for behaviour or information architecture. Verify commands, paths,
defaults, schemas, and terminology against v2. Adopt a passage or presentation choice only when it
fits the accepted site design and improves the target page. Rewrite, split, or reject it otherwise.

When code cannot supply a necessary field description, improve the field or object documentation
beside the code in a documentation-only commit. Do not change runtime behaviour to make generated
documentation easier to render.

## Vale and verification

The repository contains `.vale.ini`, copied temporarily from `apply-coding-rules`. `mise.toml`
installs Vale, and `.styles/` is ignored because `vale sync` generates it locally.

The Vale configuration checks Markdown and Python prose with the pinned `ai-tells` packages. It
disables checks that conflict with accepted project prose. Vale supplements review; it does not
override a technically necessary qualification or the prose rules in this file.

Run Vale after changing prose:

```bash
mise install
mise exec -- vale sync
mise exec -- vale docs design/documentation-site.md CONTRIBUTING.md
```

Run it against the changed Python files as well when a documentation change edits docstrings or
comments. Examine each suggestion and change the prose only when the finding applies. Do not make a
sentence less precise to silence a checker.

Run focused checks while editing, then complete this sequence before presenting a phase as done:

```bash
mise exec -- vale <changed-prose-files>
mise run docs
mise run format
```

The site review also checks:

- Navigation and page titles.
- Internal links, anchors, instant previews, and API cross-references.
- Code annotations and linked tabs.
- Generated API fields and signatures.
- Search terms and tags.
- Desktop and mobile layout.
- Light and dark colour schemes.
- Keyboard navigation and visible focus.
- Diagram and image alternatives.
- The complete quickstart command sequence.

## Agent guidance

The documentation worktree contains a local copy of `agent_docs/` from the `apply-coding-rules`
worktree. The directory is ignored by git until the same guidance reaches `origin/v2`. The
coordinator verifies the copy against `apply-coding-rules` before dispatching documentation work.

Every agent reads these files completely before editing:

- `agent_docs/index.md`
- `agent_docs/writing-and-docs.md`
- `agent_docs/lint.md`

The work packet names any other topic guide that applies. An agent changing a Python API or
docstring also reads the relevant architecture and data guides. An agent changing commands or
configuration reads `agent_docs/cli-config-runtime.md`.

When `origin/v2` contains tracked agent guidance, refresh the worktree and use the upstream files.
Do not retain a separate local version after that point.

## Migration from `more-docs`

### Migration rules

1. Work only in the `origin/v2` documentation worktree after this specification is accepted.
2. Treat `origin/v2` code and tests as the behaviour baseline. Treat `more-docs` only as candidate
   prose and presentation material.
3. Do not merge or rebase `more-docs` into the documentation branch.
4. Do not cherry-pick its commits as a group.
5. Assess content by subject. Adopt, rewrite, split, or reject it after checking v2 and this
   specification.
6. Record a disposition for every source page and branch-only documentation change.
7. Do not migrate unrelated Python behaviour changes.
8. Stop using the `more-docs` checkout after every ledger entry has a destination or an explicit
   rejection.

### Committed branch changes

Review the eight commits unique to `more-docs` independently. A listed use is an assessment target,
not an instruction to retain the change:

| Commit     | Subject                                              | Assessment target                                                                     |
| ---------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `cdb821b1` | Add `griffe-pydantic`                                | Reapply only if the selected schema rendering requires it. Update the lock from v2.   |
| `482aa2f4` | Add the repository header link                       | Check whether the header link fits the accepted navigation.                           |
| `9dce08c6` | Add object docstrings                                | Check each description against its current v2 object. Exclude runtime changes.        |
| `9dbb84c9` | Change documentation design                          | Review each style and configuration change against the Zensical conventions above.    |
| `f55a8423` | Add pairing abbreviations                            | Check the terms, then place useful definitions in abbreviations or the glossary.      |
| `7f04552c` | Add experiment hierarchy and specification reference | Assess as candidate content for concepts and grouped schema reference.                |
| `721f2ca0` | Adjust heading spacing                               | Retain only if visual checks show the theme needs the override.                       |
| `8753f455` | Change ignored files                                 | Do not migrate unless the documentation worktree creates the same generated artifact. |

### Page migration ledger

Source paths in this table identify the pre-alignment material that was assessed. Target paths are
the current destinations.

The first implementation phase expands this table when a source section splits across targets.
Targets identify where a subject belongs if the source material is accurate and useful. They do
not require the source wording or structure to be retained.

| Source                                                   | Target                                                                                     | Assessment                                                                                                                                                              |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/index.md`                                          | `docs/index.md`                                                                            | Verify the description and assess it as input to a goal-based home page.                                                                                                |
| `docs/get-started.md`                                    | `docs/start-here/install-and-check.md` and `run-quickstart.md`                             | Account for acquisition, requirements, KTANE, services, displays, prior artifacts, and contextual admonitions after checking v2.                                        |
| `docs/running/index.md`                                  | `docs/run-and-submit/index.md`                                                             | Replace the thin index with workflow routing.                                                                                                                           |
| `docs/running/add-new-player.md`                         | `docs/run-and-submit/add-model.md` and `configure-provider.md`                             | Assess scaffolding, identity, settings, providers, capabilities, token measurement, validation, tabs, questions, examples, and warnings. Split useful material by task. |
| `docs/running/run-your-model.md`                         | `create-run-manifest.md`, `run-interactive.md`, and `inspect-results.md`                   | Account for manifest, identity, validation, generation, execution, resume, and results. Link exact fields to reference.                                                 |
| `docs/submit-your-results.md`                            | `docs/run-and-submit/submit-results.md`                                                    | Reconcile candidate material with the release-bound v2 workflow. Account for validation and protected-content warnings.                                                 |
| `docs/manuals.md`                                        | `run-and-submit/prepare-manuals.md`, `understand/manuals-and-rule-seeds.md`, and reference | Separate useful procedure, concept, and configuration material. Verify offline and recovery behaviour.                                                                  |
| `docs/concepts/*` on `more-docs`                         | `docs/understand/*`                                                                        | Assess hierarchy explanations against v2 and the accepted concept-page rules.                                                                                           |
| `docs/guides/*` in the working tree                      | `docs/understand/*`                                                                        | Assess comparability, runtime, hierarchy, and result explanations after checking v2.                                                                                    |
| `docs/tutorial/run-the-benchmark.md` in the working tree | `docs/start-here/run-quickstart.md`                                                        | Combine with the v2 quickstart instead of retaining a separate tutorial section.                                                                                        |
| `docs/how-to/*` in the working tree                      | `docs/run-and-submit/*`                                                                    | Assess task-specific content and return useful FAQ material to its subject.                                                                                             |
| `docs/submit-results/*` in the working tree              | `docs/run-and-submit/submit-results.md`                                                    | Reconcile with `origin/v2`. The release workflow has priority where behaviour differs.                                                                                  |
| `docs/reference/*` in the working tree                   | `docs/reference/*`                                                                         | Assess overview prose and object selection. Use domain grouping instead of class-per-page navigation.                                                                   |
| `docs/design/manual-system.md` in the working tree       | Product design input, manuals concept, and reference                                       | Do not publish the implementation plan wholesale. Extract accepted behaviour after checking v2.                                                                         |
| `docs/_templates/*` in the working tree                  | Zensical `mkdocstrings` templates                                                          | Retain only overrides required by the selected grouped API rendering.                                                                                                   |
| `docs/stylesheets/extra.css` and `zensical.toml` changes | Site foundation                                                                            | Apply by feature and verify each override in both colour schemes and mobile layout.                                                                                     |
| Python docstring changes in `more-docs`                  | Current v2 objects                                                                         | Consider only descriptions that match the current object and add information beside it.                                                                                 |
| Other Python changes in the working tree                 | No documentation destination                                                               | Exclude unless approved as a separate behaviour change.                                                                                                                 |

### FAQ reversal ledger

Remove `docs/faq.md` after moving every entry:

| FAQ subject                                  | Canonical destination                                                        |
| -------------------------------------------- | ---------------------------------------------------------------------------- |
| Whether Docker is required                   | `Start here` infrastructure section with a `question` admonition.            |
| Default Redis authentication                 | Redis and runtime-services setup, with the network exposure warning visible. |
| Running without exported telemetry           | `Start here` and observability configuration using linked alternatives.      |
| Whether `mise` is required                   | Installation tabs for `mise` and direct `uv`.                                |
| Removing Parquet files after building DuckDB | Results and storage concept plus output-file reference.                      |
| What `gptnt run` starts                      | Interactive-run procedure, runtime concept, and CLI reference at each level. |

Preserve the original contextual admonitions from `origin/v2`. The migration may improve their
titles and types but must not move their information to a general question collection.

### Working-tree material

The uncommitted `more-docs` checkout contains new pages, generated-reference stubs, styles,
templates, and some Python changes. Before editing a target subject:

1. Compare the v2 page, committed `more-docs` content, and working-tree content.
2. List every distinct section in the migration ledger.
3. Select the accurate passages and Zensical components.
4. Rewrite them into the target page instead of copying the old file layout.
5. Verify the finished target against v2.
6. Record an adopt, rewrite, split, or reject disposition with the reason.

Once all material has a recorded disposition, the documentation worktree is the only active site
workspace. Archive or delete `more-docs` only through a separate, explicit repository operation.

## Multi-agent execution

Use this file as the coordination record when several agents work on the site. Every agent reads
this file completely before editing. The coordinating agent gives each worker a bounded work packet
and remains responsible for integration decisions.

Keep one agent slot for coordination and use up to three worker agents at once. Organise authored
work as connected reader journeys that cross procedures, concepts, reference, and troubleshooting.
Do not assign one agent to write all concepts while another writes all reference pages without
connecting them during drafting.

Agents communicate dependencies, target page names, anchors, terminology, and cross-link requests
while they work. The coordinator integrates shared changes after each checkpoint rather than
waiting until every page is drafted.

### Coordinator responsibilities

The coordinating agent owns:

- This specification and its migration ledger.
- `zensical.toml` and top-level navigation.
- Shared templates, includes, styles, and JavaScript.
- The controlled tag vocabulary.
- Cross-section naming and URL decisions.
- A connection ledger recording required relationships among pages and workstreams.
- Final link, build, visual, Vale, and repository checks.

A worker reports proposed changes to a coordinator-owned file rather than editing it unless the
work packet assigns that file for the duration of the task.

### Work packet

Every delegated task states:

1. The reader journey, objective, and expected outcome.
2. The exact files the agent owns across procedures, concepts, reference, and troubleshooting.
3. The v2 implementation, tests, templates, and existing pages that provide evidence.
4. The `more-docs` pages or sections to assess as optional source material.
5. The required inbound links, outbound links, shared terms, and canonical explanations.
6. Files the agent must not edit.
7. Focused technical, prose, and rendering verification to run.
8. The checkpoints and handoff information the coordinator needs.

Do not delegate an open-ended request such as "improve the reference". Divide it by interface
inventory or domain.

### Stage 1: evidence map and shared foundation

The first stage does not contain a separate worker-validation wave. While the coordinator refreshes
the branch and prepares shared files, three workers gather the evidence needed to finish the
foundation:

| Worker | Assignment                                                                                                       | Output                                                                               |
| ------ | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| A      | Assess `origin/v2` and every `more-docs` section                                                                 | Section-level candidate ledger with adopt, rewrite, split, or reject recommendations |
| B      | Inventory v2 commands, configuration, persisted formats, Python extension points, and runtime subsystems         | Reference coverage inventory and grouped-rendering requirements                      |
| C      | Trace the runner, model-integrator, submitter, and contributor journeys; match each need to a Zensical component | Journey map, connection requirements, and component matrix                           |

The checked Stage 1 evidence packets are:

- [Documentation migration ledger](documentation-migration-ledger.md), which records section-level
  dispositions, restored FAQ subjects, canonical ownership, and implementation-evidence keys.
- [Documentation reference coverage inventory](documentation-reference-coverage.md), which records
  the selected CLI, configuration, format, Python, and runtime interfaces.
- [Documentation reader journeys and component map](documentation-reader-journeys.md), which records
  the three vertical slices, cross-slice connections, navigation needs, and bounded Zensical uses.

The coordinator combines those outputs and completes these foundation tasks:

- Refresh from `origin/v2` and reconcile the temporary Vale and agent-guidance copies.
- Confirm top-level labels, paths, page metadata, tags, and icons.
- Configure navigation, search, content components, and shared presentation.
- Establish abbreviations, glossary ownership, templates, and styles.
- Prove grouped `mkdocstrings` rendering on one representative schema and one Python extension page.
- Record the page connection ledger before parallel authoring begins.

Do not create empty sections that promise pages unavailable in the same integration checkpoint.

### Stage 2: connected vertical slices

After the shared foundation works, three agents author connected slices in parallel. Each slice
contains the relevant workflow, concepts, reference, and troubleshooting rather than one page type
in isolation.

| Slice                                 | Procedure ownership                                                           | Concept ownership                                                  | Reference ownership                                                               | Troubleshooting ownership                                                     |
| ------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| A: first run and runtime orientation  | `Start here` installation, checks, and quickstart                             | Benchmark and player model, experiment hierarchy, runtime services | `doctor`, `generate`, `run`, environment requirements, and runtime implementation | Installation, game, displays, Redis, and service startup                      |
| B: model integration and manuals      | Add a model, configure a provider, prepare manuals, and create a run manifest | Roles, protocols, capabilities, manuals, and rule seeds            | Player, provider, manual, run-manifest, and supported extension interfaces        | Provider, model response, capabilities, and manual preparation                |
| C: execution, results, and submission | Interactive runs, statics, result inspection, analysis, and submission        | Suites, revisions, comparability, results, and provenance          | Execution, statics, results, submission commands, schemas, and output formats     | Interrupted runs, missing outputs, result building, and submission validation |

The coordinator owns home and section indexes, `zensical.toml`, shared assets, the glossary, the tag
vocabulary, and cross-slice navigation. A work packet lists the exact files within each slice so two
agents never edit the same page.

### Connection checkpoints

Connection work happens during authoring:

1. **Contract checkpoint:** Before drafting, slice owners agree on shared terms, page names,
   prerequisites, outputs, and the links crossing slice boundaries.
2. **Draft checkpoint:** When a page establishes a heading or anchor another slice needs, its owner
   reports it immediately. The coordinator updates the connection ledger and routes any shared-file
   change.
3. **Journey checkpoint:** After each slice has a connected draft, agents follow another slice's
   reader path. Agent A checks the path from first run into model integration. Agent B checks the
   path from configuration into execution and submission. Agent C checks the path from results back
   to benchmark, runtime, and comparability explanations.
4. **Integration checkpoint:** Owners correct missing prerequisites, duplicated explanations,
   terminology mismatches, and dead-end pages. The coordinator then updates navigation and shared
   indexes before the next batch.

Maintain the connection ledger in this form:

| Source page | Reader need | Target page or anchor | Source owner | Target owner | Status |
| ----------- | ----------- | --------------------- | ------------ | ------------ | ------ |

### Stage 3: reference and coverage closure

After the connected slices are drafted, reassign the workers by reference inventory:

- Agent A closes CLI and configuration coverage.
- Agent B closes persisted-file, schema, database, and output coverage.
- Agent C closes supported Python and runtime implementation coverage.

This stage checks and completes the reference already connected to the reader journeys. It does not
start a second, isolated reference site. Each agent follows reference links back to the relevant
procedure and concept before marking an inventory entry complete.

### Stage 4: final technical, prose, and presentation gates

Freeze authored content before the final gates so later edits do not invalidate an earlier pass.

1. **Technical accuracy:** An agent other than the author checks commands, fields, defaults,
   examples, file paths, generated API output, and failure behaviour against v2 code and tests.
2. **Site-wide prose edit:** One agent owns all public prose temporarily and reads every changed page
   in navigation order. The agent applies `agent_docs/writing-and-docs.md` and checks page purpose,
   paragraph order, headings, literal wording, sentence boundaries, terminology, link text,
   admonition type, tab use, British English, and unnecessary repetition.
3. **Independent consistency read:** A different agent reads the edited site without changing it.
   The agent reports undefined terms, duplicated canonical explanations, inconsistent names,
   unsupported claims, abrupt transitions, and pages whose next action is unclear.
4. **Procedure and connection check:** The remaining agent follows the runner, model-integrator, and
   submitter journeys, including troubleshooting and deep reference links.
5. **Automated prose check:** Run Vale across all changed Markdown and changed Python docstrings or
   comments. Correct supported findings, then rerun Vale after every prose correction batch.
6. **Rendering and repository check:** Build Zensical, inspect desktop and mobile layouts in both
   colour schemes, test keyboard navigation, search, tabs, previews, diagrams, and generated API,
   then run repository formatting and affected tests.

Vale is not a substitute for the two editorial passes. Do not invoke the `review-gptnt-change`
skill for this documentation programme; use the technical, prose, connection, and rendering gates
defined here.

### Shared-worktree rules

- Assign one owner to each file for a coordination cycle.
- Check `git status --short` before editing and preserve changes outside the work packet.
- Treat the `more-docs` checkout as read-only migration input. Do not edit, format, stash, clean, or
  commit it while migration remains incomplete.
- Do not revert, format, stage, or commit another worker's changes.
- Do not edit `zensical.toml`, shared includes, styles, templates, the glossary, or this file unless
  the work packet assigns that file.
- Send a requested cross-link, glossary entry, abbreviation, tag, or navigation change to the owner
  in the handoff.
- Verify source material against v2 independently. Do not accept another agent's summary as the only
  evidence for a command, field, default, or format.
- Do not copy an entire `more-docs` page into the target layout. Migrate the assigned subjects and
  report the disposition of every assessed section.
- Do not change Python behaviour during documentation work. A source edit is limited to a verified
  docstring or field description unless the user approves a separate implementation task.
- Do not begin work whose dependency is incomplete. Report the dependency instead of inventing a
  temporary structure that another agent must remove.

### Handoff

Every worker returns:

- Files changed.
- Source sections adopted, rewritten, split, or rejected, including the reason for the disposition.
- Implementation and tests consulted.
- Commands and examples verified.
- Checks run and their results.
- Requested changes to coordinator-owned files.
- Unresolved decisions or cross-workstream dependencies.

The coordinator verifies the handoff against the diff and updates the migration ledger. A handoff
does not mark a phase complete by itself.

## Delivery plan

All phases run in the documentation worktree. Keep commits limited to one phase or one coherent
domain so a review can identify the source material and verification performed.

### Phase 0: establish the specification and checks

- [x] Create the v2 documentation worktree.
- [x] Add this specification.
- [x] Copy the temporary Vale configuration from `apply-coding-rules`.
- [x] Copy the current ignored `agent_docs/` from the `apply-coding-rules` worktree.
- [x] Run Vale and focused repository checks after the expanded plan is complete.
- [ ] Review and accept the specification before migrating pages.

### Phase 1: build the evidence map and shared foundation

- [ ] Refresh the branch from `origin/v2`. If upstream now contains the Vale setup, keep the
      upstream version and remove any duplicate temporary change.
- [ ] Dispatch the three evidence assignments and integrate their outputs.
- [ ] Expand the `more-docs` ledger to section level with adopt, rewrite, split, or reject status.
- [ ] Record which v2 interfaces the reference must cover.
- [ ] Record the reader journeys and page connection ledger.
- [ ] Configure navigation, page metadata, tags, icons, search, and Zensical content features.
- [ ] Establish abbreviations, glossary ownership, templates, styles, and shared assets.
- [ ] Decide between native Mermaid and the existing enhancement using the stated criteria.
- [ ] Prove grouped `mkdocstrings` output for one schema and one supported Python extension point.
- [ ] Build section indexes only when their first connected pages are ready.

### Phase 2: author the connected slices

- [ ] Agree on cross-slice contracts before drafting.
- [ ] Complete Slice A: first run and runtime orientation.
- [ ] Complete Slice B: model integration and manuals.
- [ ] Complete Slice C: execution, results, and submission.
- [ ] Restore each useful contextual admonition on its subject page.
- [ ] Report new anchors and cross-link dependencies while drafting.
- [ ] Run focused Vale, build, and evidence checks for every handed-off page batch.

### Phase 3: connect the journeys and close reference coverage

- [ ] Run the rotated journey checks across all three slices.
- [ ] Resolve missing prerequisites, dead ends, terminology mismatches, and duplicate explanations.
- [ ] Complete the CLI and configuration inventory.
- [ ] Complete the persisted-file, schema, database, and output inventory.
- [ ] Complete the supported Python and runtime implementation inventory.
- [ ] Link every reference domain back to its relevant procedure and concept.
- [ ] Add a coverage check that detects an undocumented selected interface.
- [ ] Remove the FAQ after every useful item has a canonical destination.
- [ ] Confirm that every `more-docs` source section has an explicit disposition.

### Phase 4: complete the final gates

- [ ] Freeze page ownership and authored content.
- [ ] Run a non-author technical accuracy pass for every page.
- [ ] Run the site-wide prose edit in navigation order.
- [ ] Run the independent terminology, duplication, and transition read.
- [ ] Follow the runner, model-integrator, and submitter journeys from home to completion.
- [ ] Run Vale across all changed Markdown and changed Python prose, correct supported findings, and
      rerun it.
- [ ] Check navigation, links, anchors, previews, tabs, annotations, search, tags, and glossary.
- [ ] Check desktop, mobile, both colour schemes, keyboard access, images, diagrams, and generated
      API output.
- [ ] Run the Zensical build, repository formatting, and affected tests.

## Completion criteria

The documentation expansion is complete when:

- The top-level site follows the information architecture in this file.
- A new reader can install, check, and complete the quickstart without using source code to discover
  a required step.
- A model integrator can configure, run, inspect, and submit a model through linked procedures.
- Every FAQ entry has returned to its canonical subject and the FAQ page is removed.
- Every `more-docs` page, documentation commit, and working-tree documentation section has an
  adopt, rewrite, split, or reject disposition.
- Reference covers the selected CLI, configuration, persisted formats, Python API, and runtime
  implementation inventory.
- Generated API detail comes from v2 source and is grouped beneath hand-written domain overviews.
- Contributor depth remains reachable through navigation, search, cross-links, and controlled
  tags.
- Admonitions, tabs, annotations, diagrams, tooltips, footnotes, links, previews, and images follow
  the conventions in this file.
- No analytics or analytics-backed feedback is configured.
- A site-wide editor has read every changed public page in navigation order and applied the prose
  rules in this file and `agent_docs/writing-and-docs.md`.
- A separate consistency read has checked terminology, canonical explanations, repetition,
  transitions, and next actions.
- Vale has no supported finding in the changed prose.
- The Zensical build succeeds without unresolved internal links or API references.
- The affected repository checks pass.

## Maintenance

Update the relevant procedure and reference in the same change as a new or changed CLI command,
configuration field, persisted format, or supported Python interface.

Update this specification when changing top-level navigation, page types, progressive exposure,
reference policy, Zensical conventions, prose rules, migration scope, or completion criteria. Do
not use it as a log of minor wording changes.

When tracked agent guidance becomes available on `origin/v2`, add a short pointer to this file from
the documentation section of that guidance. Keep the complete site policy here rather than copying
it into agent instructions.
