---
title: Manual configuration
tags:
  - Configuration
---

# Manual configuration

Manual profiles under `configs/manual/` define ordered handbook content. The repository-level
`configs/manual/sources.toml` pins remote sources and describes official-manual page ranges.

## Profile schema

::: gptnt.ktane.manuals.profile.ManualProfile
    options:
      heading_level: 3
      show_root_heading: true
      show_source: false
      members: false

`documents` contains one or more entries in output order. `include_frontmatter` inserts the
configured frontmatter for the profile language.

### Document variants

::: gptnt.ktane.manuals.profile.OfficialDocument
    options:
      heading_level: 4
      show_root_heading: true
      show_source: false
      members: false

::: gptnt.ktane.manuals.profile.KtaneContentDocument
    options:
      heading_level: 4
      show_root_heading: true
      show_source: false
      members: false

::: gptnt.ktane.manuals.profile.KtaneContentAppendix
    options:
      heading_level: 4
      show_root_heading: true
      show_source: false
      members: false

::: gptnt.ktane.manuals.profile.LocalDocument
    options:
      heading_level: 4
      show_root_heading: true
      show_source: false
      members: false

All effective documents and optional frontmatter must use one language. A relative local path is
resolved from the checkout root and must end in `.html`. Its local dependencies must stay beside or
below the document.

## Source catalog

::: gptnt.ktane.manuals.sources.ManualSources
    options:
      heading_level: 3
      show_root_heading: true
      show_source: false
      members: false

The catalog schema version is `1`. Its KtaneContent commit is a full 40-character Git commit. The
catalog also defines the official manual URLs and page maps, catalog URL, and language-specific
frontmatter.

!!! info "Provider-owned formats stay external"
    The catalog records URLs and pins, but GPTNT does not redefine the remote repositories or PDF
    formats behind them.

## Rule-seed constraint

GPTNT v2 manual resolution supports only rule seed `1`. A manual-bearing experiment with another
rule seed fails during preparation.

Use [Prepare manuals](../../manuals.md) to edit and compile a profile. The
[manual file reference](../files/manuals.md) describes persisted inputs and cache outputs.
