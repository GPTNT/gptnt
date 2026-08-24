---
title: Prepare manuals
tags:
  - CLI
  - Configuration
---

# Prepare manuals

GPTNT prepares the manual artefact required by each remaining experiment before it starts game or
player processes. A standard `gptnt run` performs this preparation. Use the standalone manual
commands when you need to populate an offline cache or isolate a preparation failure.

## Before you begin

Install the project and Playwright-managed Chromium:

```bash title="Install dependencies"
mise run sync
```

Chromium compiles profiles that contain KtaneContent or local HTML. A profile made only from pages
of official PDF manuals does not start the browser.

!!! warning "Prepare the browser before going offline"
    The browser is stored outside `output/manual_cache/`. Install Chromium on the destination
    machine before it loses network access, even when you intend to copy a complete cache.

## Select the manual profile

Manual profiles live in `configs/manual/`. A suite selects its profile through Hydra defaults:

```yaml title="configs/suite/<suite>.yaml" annotations
defaults:
  - /manual@suite.manual_profile: vanilla # (1)!
```

1. Use the profile filename without `.yaml`.

The included profiles are `vanilla`, `vanilla_with_needy`, and `vanilla_fr`. A profile change
changes measured suite content. Update the suite revision, freeze the suite, and regenerate its
experiment specifications before running it.

## Let the run prepare required manuals

Run persisted experiment specifications in the standard way:

```bash title="Run with automatic preparation"
gptnt run runs/<name>.yaml
```

GPTNT applies doctor checks and resume filtering first. It then prepares each distinct manual
profile required by the work that remains. Preparation completes before the experiment manager,
game rooms, or players start. `--force` does not bypass a preparation failure.

!!! success "Manual preparation is complete"
    The run proceeds to the process plan after every required profile resolves to a validated
    artefact. Only protocols with `include_manual: true` receive that artefact.

## Prepare manuals without starting a run

Compile the profiles used by all configured suites:

```bash title="Compile configured manuals"
gptnt manual compile
```

Narrow preparation by repeating `--suite`, or select every profile:

```bash title="Select manual profiles"
gptnt manual compile --suite single-pairwise-sync --suite multi-self-sync
gptnt manual compile --all-profiles
```

Use `download` to stop after remote sources enter the cache:

```bash title="Download manual sources"
gptnt manual download --suite single-pairwise-sync
```

`--suite` and `--all-profiles` are mutually exclusive. Without either option, both commands select
the profiles used by all configured suites. Shared profiles are prepared once.

!!! success "The cache is ready"
    A complete compile writes a validated artefact under `output/manual_cache/artifacts/<sha256>/`.
    The directory contains `manifest.json`, `handbook.pdf`, and numbered page text and images.

## Prepare an offline machine

On a connected machine, compile the suites that the offline machine will run:

```bash title="Compile selected profiles"
gptnt manual compile --suite single-pairwise-sync --suite multi-self-sync
```

Copy the complete `output/manual_cache/` directory to the same path in the offline checkout. Copy
local HTML inputs and their referenced files to the paths recorded in the profile as well. Keep the
Python environment, Playwright version, cached data, configuration, and checkout content aligned
with the connected installation.

Run the compile command on the destination before starting the benchmark. A cache hit verifies that
the copied artefact and its inputs match.

## Author another profile

Create `configs/manual/<name>.yaml` and list at least one document in output order:

```yaml title="configs/manual/custom.yaml" annotations
include_frontmatter: false

documents:
  - source: ktanecontent # (1)!
    id: Wires
    language: en

  - source: local # (2)!
    id: CustomModule
    language: en
    path: manuals/custom-module.html
```

1. A KtaneContent module uses a catalog ID. Set `document` to a bare `.html` filename when the
   selected language needs an explicit document.
2. A local document path is relative to the checkout root, ends in `.html`, and owns only
   dependencies beside or below that file.

Every document and the optional frontmatter must use one language. Official manual entries must
match a language, module ID, and page range in `configs/manual/sources.toml`. Appendices use a
KtaneContent document without a module ID.

Select the new profile in a suite. Then freeze the changed suite, regenerate its specifications,
and compile the profile through that suite:

```bash title="Retry manual compilation"
gptnt manual compile --suite <suite>
```

For exact profile and source fields, see the
[manual configuration reference](../reference/configuration/manuals.md). For cache contents, see
[manual files](../reference/files/manuals.md). If preparation stops, start with
[manual preparation troubleshooting](../troubleshooting/manual-preparation.md).
