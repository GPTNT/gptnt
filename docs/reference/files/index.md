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
| [Experiment specifications](experiment-specifications.md){data-preview} | Generated attempt inputs and frozen suite, mission, and player state |
| [Player records and outcomes](player-records-and-outcomes.md){data-preview} | Per-turn Parquet rows, terminal footers, summaries, and outcomes |
| [DuckDB](duckdb.md){data-preview} | Tables built from player-record Parquet for result analysis |
| [Static evaluation outputs](static-evaluation-outputs.md){data-preview} | Metadata, predictions, metrics, and `how-do-you` output |
| [Submission bundles](submission-bundles.md){data-preview} | Schema-version-2 manifests and interactive or static payloads |
| [Output layout](output-layout.md){data-preview} | Default locations and ownership of generated files |

Run manifests and player settings are covered by the
[configuration reference](../configuration/index.md). Runtime-only Redis values are covered by the
[runtime implementation reference](../runtime/index.md).

!!! info "Authored input and cache output"
    Commit manual profiles and `sources.toml` when they define benchmark content. Treat
    `output/manual_cache/` as derived data: copy it for offline preparation, but do not edit its
    manifests or compiled files by hand.
