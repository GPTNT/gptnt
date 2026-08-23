---
title: Files and schemas
tags:
  - Reference
---

# Files and schemas

These pages describe authored files and persisted outputs that cross a GPTNT command or process
boundary. Configuration model pages describe their validated fields; this section describes names,
locations, and on-disk relationships.

## Available file contracts

| Files | Contract |
| ----- | -------- |
| [Manuals](manuals.md){data-preview} | Manual profile inputs and derived outputs |

Run manifests and player settings are covered by the [configuration reference](../configuration/index.md).
Runtime-only Redis values are covered by the [runtime implementation reference](../runtime/index.md).

!!! info "Authored input and cache output"
    Commit manual profiles and `sources.toml` when they define benchmark content. Treat
    `output/manual_cache/` as derived data: copy it for offline preparation, but do not edit its
    manifests or compiled files by hand.
