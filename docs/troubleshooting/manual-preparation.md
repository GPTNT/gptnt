---
title: Manual preparation
tags:
  - Troubleshooting
---

# Manual preparation

Manual failures occur before game and player processes start. Use the error's profile name, entry
index, source path, or artefact key to narrow the correction.

## No profile is selected

`gptnt manual compile --suite <suite>` rejects an unknown suite. Confirm the available name with:

```bash title="List manual suites"
gptnt list suites
```

With `--all-profiles`, GPTNT selects every profile file whose name does not begin with an
underscore. With no selection option, it selects profiles used by configured suites. A repository
with no profiles for the chosen mode cannot prepare a manual.

Do not combine `--suite` and `--all-profiles`.

## A remote source is unavailable

On a connected machine, populate the source cache:

```bash title="Download manual sources"
gptnt manual download --suite <suite>
```

If the source URL or pinned KtaneContent commit is wrong, correct `configs/manual/sources.toml` and
repeat the download. Keep a full 40-character commit pin.

For an offline machine, compile on a connected machine and copy the complete
`output/manual_cache/` directory to the same path. Copying only one downloaded file can leave
resolution without source catalog data or required compiler and PDF inputs.

## Chromium is missing

The error names the Playwright browser executable. Install the version paired with the current
environment:

```bash title="Install Chromium"
uv run playwright install chromium
```

Repeat the installation after changing the Playwright version. Profiles made only from official PDF
pages do not require the browser. KtaneContent and local HTML profiles do.

## Resolution names `documents[n]` or `frontmatter[n]`

Correct the referenced entry in the profile or source catalog:

- Use a module ID present in the selected KtaneContent catalog or official-manual page map.
- Use a bare `.html` filename for an explicit KtaneContent document.
- Point a local entry to an existing `.html` file relative to the checkout root.
- Keep local images, style sheets, and scripts beside or below the local document.
- Configure frontmatter for the same language as the documents.

Run the compile command again after correcting it.

## Documents use different languages

Every effective document in one profile must use the same language, including frontmatter. Change
the mismatched entry or disable frontmatter when the catalog has no matching language entry.

## A rule seed cannot be resolved

GPTNT v2 prepares manual-bearing experiments only for rule seed `1`. Update the mission and
regenerate its experiment specifications if another value was set unintentionally.

Changing a rule seed changes benchmark identity. Do not edit a persisted specification to bypass
the check.

## Local HTML compilation reports a missing dependency or request

Local HTML may load only dependencies beside or below its configured file. Move a required local
asset inside that tree and use a local relative reference. Remove network requests and other
external run-time dependencies from the document.

The compiler also stops on missing images and uncaught page JavaScript errors. Correct the first
reported failure, then run:

```bash title="Compile the manual"
gptnt manual compile --suite <suite>
```

## A cached artefact is incomplete or changed

Rerun the compile command. GPTNT validates the manifest and file hashes. It removes an invalid
artefact directory before rebuilding it. If rebuilding fails, correct the source or browser error
from that attempt instead of editing `manifest.json`.

## A cached source file is damaged

While connected, remove only the source file named by the error. Then run `manual download` or
`manual compile` for the affected suite. Copy the refreshed complete cache to offline machines.

Use [Prepare manuals](../run-and-submit/prepare-manuals.md) for the standard workflow and
[manual files](../reference/files/manuals.md) for the cache contract.
