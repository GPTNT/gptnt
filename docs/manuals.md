# Manuals

GPTNT builds the manual required by each experiment from a selected manual profile. A normal
`gptnt run` prepares these manuals before it starts the experiment processes.

## Select a profile

Manual profiles live in `configs/manual/`. The shipped profiles include `vanilla.yaml`,
`vanilla_with_needy.yaml`, and `vanilla_fr.yaml`.

Each suite selects a profile in its Hydra defaults. For example:

```yaml
defaults:
  - /manual@suite.manual_profile: vanilla
```

Change `vanilla` to the filename without `.yaml` to select another profile. A profile change alters
the measured suite content, so update the suite revision, run `gptnt suite freeze`, and regenerate
the experiment specs before running them.

## Install Chromium during setup

Install the project dependencies and Playwright-managed Chromium together:

```bash
mise run sync
```

If the Python dependencies are already installed, install the matching browser directly:

```bash
uv run playwright install chromium
```

Chromium is required to compile a profile that contains HTML from KtaneContent or a local file. A
profile made only from official PDF pages does not use the browser.

## Run the benchmark

Run the generated specs normally:

```bash
gptnt run runs/<name>.yaml
```

After doctor and resume filtering, GPTNT downloads missing remote source files, resolves each
distinct profile required by the remaining experiments, and compiles its manual. This preparation
finishes before the experiment manager, game rooms, or players start. `--force` does not bypass it.

You do not need to download or compile manuals before a normal run. The standalone commands remain
available for preparing an offline machine or diagnosing one stage:

```bash
gptnt manual compile
gptnt manual compile --suite single-pairwise-sync --suite multi-self-sync
gptnt manual compile --all-profiles

gptnt manual download --suite single-pairwise-sync
```

With no selection flag, both commands prepare the profiles used by every configured suite. Repeat
`--suite` to select suites, or use `--all-profiles` to include profiles that no suite selects. The
two selection modes cannot be combined. `manual compile` performs the complete download, resolve,
and compile path. `manual download` stops after caching remote source files.

## Understand the cache

GPTNT stores manual data under `output/manual_cache/`:

- `sources/` contains downloaded KtaneContent files, official PDFs, and the HTML compiler sources.
- `artifacts/` contains compiled manuals and their page text and images.

GPTNT reuses downloaded files when they are present. It validates a compiled artifact before reuse
and rebuilds it if any required output is missing or changed. Local HTML files and their referenced
files stay at their configured paths; GPTNT does not copy them into the cache.

## Prepare an offline machine

On a connected machine, compile the suites that the offline machine will run:

```bash
gptnt manual compile --suite single-pairwise-sync --suite multi-self-sync
```

Copy the complete `output/manual_cache/` directory to the same path in the offline checkout. Also
copy any local HTML inputs and their referenced files to the paths recorded in the profile.

Playwright stores its managed browser outside this directory. Run the Chromium installation step
on the destination before it goes offline so it can rebuild an HTML artifact if necessary. Keep the
Python environment, Playwright version, cached data, configs, and checkout content from the same
GPTNT installation.

## Repair preparation failures

The preparation error identifies the profile entry, source file, browser, or artifact that stopped
the run. Correct that item, then rerun `gptnt manual compile --suite <suite>` before retrying the
benchmark.

| Failure | Repair |
| --- | --- |
| An input is unsupported or cannot be resolved | Correct the named `documents[n]` entry. Use one language throughout the profile, an ID present in KtaneContent or the configured official manual, an explicit translated KtaneContent filename, or an existing local `.html` file with all of its local dependencies. |
| A remote source is missing | On a connected machine, run `gptnt manual download --suite <suite>` or `gptnt manual compile --suite <suite>`. On an offline machine, restore the complete cache from the connected machine. |
| Playwright-managed Chromium is missing | Run `uv run playwright install chromium` in the environment that runs GPTNT. Repeat this after changing the Playwright version. |
| A compiled artifact is incomplete | Rerun the compile command. GPTNT removes the invalid artifact and rebuilds it. If the rebuild fails, correct the source or browser error reported during that attempt. |
| A cached source file is damaged or stale | Remove only the named source file while connected, then run the download or compile command again. Copy the refreshed complete cache to any offline machine. |

HTML compilation rejects missing images, uncaught page JavaScript errors, and requests outside its
private compiler origin. Keep every local dependency beside or below the local document and remove
external runtime dependencies from the page.

## Author another profile

Create a YAML file under `configs/manual/`. Set `include_frontmatter`, then list at least one
document in the order it should appear:

```yaml
include_frontmatter: false

documents:
  - source: ktanecontent
    id: Wires
    language: en

  - source: local
    id: CustomModule
    language: en
    path: manuals/custom-module.html
```

All entries must use the same language. Choose each entry by source:

- A KtaneContent module uses `source`, `id`, and `language`. Add `document` with a bare `.html`
  filename for a translated page or a non-default document.
- A KtaneContent appendix has no module ID, so it uses `source`, `language`, and `document`.
- An official manual entry uses `source: official`, `id`, and `language`. The language and module ID
  must have a page range in `configs/manual/sources.toml`.
- A local entry uses `source: local`, `path`, `language`, and an optional `id`. Relative paths start
  at the GPTNT checkout root and must end in `.html`.

Set `include_frontmatter: true` only when the configured frontmatter uses the profile language.
Select the new filename in a suite, freeze the changed suite, regenerate its specs, and run
`gptnt manual compile --suite <suite>` to check the profile.
