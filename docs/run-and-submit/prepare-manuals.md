---
title: Prepare manuals
tags:
  - CLI
  - Configuration
---

# Prepare manuals

Compile the manual artefact required by each suite before running its experiments. `gptnt doctor`
validates the compiled artefact and blocks a run when it is absent or no longer matches its inputs.
Use the standalone manual commands to populate an offline cache or isolate a preparation failure.

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

The included profiles are `vanilla`, `vanilla_with_needy`, and `vanilla_fr`. A profile change or
`manual_rule_seed` change changes measured suite content. Update the suite revision, freeze the
suite, regenerate its experiment specifications, and compile the suite manual before running it.

## Compile before running

Compile the suites selected by the run manifest, then verify them with doctor:

```bash title="Compile and verify manuals"
gptnt manual compile --suite <suite>
gptnt doctor runs/<name>.yaml
gptnt run runs/<name>.yaml
```

The suite owns both its manual profile and `manual_rule_seed`. Compilation creates one artefact for
each distinct profile-and-seed pair. Doctor loads and validates the required artefacts before the
experiment manager, game rooms, or players start. `--force` does not bypass a missing or mismatched
manual artefact.

!!! success "Manual artefacts are compiled"
    Doctor permits the run after every required profile-and-seed pair resolves to a validated
    artefact. Only protocols with `include_manual: true` receive that artefact.

## Prepare manuals without starting a run

Compile the manuals used by all configured suites:

```bash title="Compile configured manuals"
gptnt manual compile
```

Narrow compilation by repeating `--suite`:

```bash title="Select manual profiles"
gptnt manual compile --suite single-pairwise-sync --suite multi-self-sync
```

Use `download` to stop after remote sources enter the cache:

```bash title="Download manual sources"
gptnt manual download --suite single-pairwise-sync
```

Without `--suite`, `manual compile` selects all configured suites. `manual download` can still use
`--all-profiles` when you need source assets for an unselected profile.

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
