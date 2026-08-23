---
title: Manual files
tags:
  - Reference
---

# Manual files

Manual preparation reads one authored profile and the shared source catalog. It writes downloaded
inputs and content-addressed artefacts below `output/manual_cache/`.

## Authored inputs

`configs/manual/<profile>.yaml` is a `ManualProfile`. It contains `include_frontmatter` and an
ordered, non-empty `documents` list:

```yaml title="configs/manual/custom.yaml"
include_frontmatter: false
documents:
  - source: official
    id: Wires
    language: en
  - source: local
    id: CustomModule
    language: en
    path: manuals/custom-module.html
```

`configs/manual/sources.toml` is a version `1` `ManualSources` catalog. Its top-level sections are:

```toml title="configs/manual/sources.toml"
version = 1

[[frontmatter]]
source = "official"
id = "Frontmatter"
language = "en"

[ktane_content]
repository = "https://github.com/Timwi/KtaneContent.git"
commit = "137cc181b37038ccefeddcb095b402aab8dff5de"

[ktane_content.catalog]
url = "https://ktane.timwi.de/json/raw"

[official_manual.en]
version = "1"
url = "https://www.bombmanual.com/print/KeepTalkingAndNobodyExplodes-BombDefusalManual-v1.pdf"

[official_manual.en.pages]
Frontmatter = { first = 1, last = 4 }
Wires = { first = 5, last = 5 }
```

The full source reference is repository-owned configuration. A KtaneContent pin is a full
40-character commit, rather than a branch or tag.

## Cache layout

The default cache has this structure:

```text
output/manual_cache/
├── sources/
│   └── <downloaded and compiler inputs>
└── artifacts/
    └── <sha256>/
        ├── manifest.json
        ├── handbook.pdf
        └── pages/
            ├── 0001.png
            ├── 0001.txt
            └── ...
```

Downloaded KtaneContent files, official PDFs, and compiler inputs live under `sources/`. Local HTML
and its local dependencies remain at their configured paths.

Each artefact directory name is its SHA-256 cache key. `manifest.json` records the artefact key,
resolved inputs, renderer identity, page count, and every output file with its SHA-256 digest.
`handbook.pdf` is the compiled handbook. Page files use four-digit, one-based names and contain the
text and PNG image supplied to the player pipeline.

GPTNT checks the manifest, required paths, and file hashes before reuse. It removes and rebuilds an
invalid artefact. A user should not update the JSON or any listed file to make validation pass.

Use the [manual configuration reference](../configuration/manuals.md) for profile fields and
[Prepare manuals](../../manuals.md) for cache preparation.
