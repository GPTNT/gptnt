# How to change KTANE game settings (audio, language, window)

The game's `playerSettings.xml` is written into the per-user config directory every time an
instance starts (via `KtaneSettings.create_settings_files()`, called from
`gptnt.ktane.process_manager` and `gptnt.interactive.entrypoints.run_game_instance`). You don't
edit that generated file directly — you set environment variables and let `KtaneSettings` render it.

## Field → env var → XML element

All variables use the `KTANE_` prefix. Defaults live on the `KtaneSettings` type
(`src/gptnt/ktane/game_settings.py`); the template is `src/gptnt/ktane/playerSettings.xml`.

| Setting       | Env var               | Default | XML element      | Notes                          |
| ------------- | --------------------- | ------- | ---------------- | ------------------------------ |
| Music volume  | `KTANE_MUSIC_VOLUME`  | `0`     | `<MusicVolume>`  | integer 0–100                  |
| SFX volume    | `KTANE_SFX_VOLUME`    | `0`     | `<SFXVolume>`    | integer 0–100                  |
| Language      | `KTANE_LANGUAGE_CODE` | `en`    | `<LanguageCode>` | see caveat below               |
| Window width  | `KTANE_GAME_WIDTH`    | `640`   | (runtime)        | also exported to `GAME_WIDTH`  |
| Window height | `KTANE_GAME_HEIGHT`   | `480`   | (runtime)        | also exported to `GAME_HEIGHT` |
| Game speed    | `KTANE_GAME_SPEED`    | `1`     | (runtime)        | multiplier                     |

Volumes outside `0–100` are rejected with a `ValidationError` at startup rather than writing an
invalid file.

## Examples

```bash
# Turn the audio on and switch to French for one run.
KTANE_MUSIC_VOLUME=40 KTANE_SFX_VOLUME=60 KTANE_LANGUAGE_CODE=fr <your run command>
```

Quick check of the rendered file without launching the game:

```bash
KTANE_MUSIC_VOLUME=40 KTANE_SFX_VOLUME=60 KTANE_LANGUAGE_CODE=fr \
  uv run python -c "from gptnt.ktane.game_settings import KtaneSettings; print(KtaneSettings().rendered_player_settings)"
```

## Supported language codes

`KTANE_LANGUAGE_CODE` is constrained to the codes KTANE ships (English plus 26 translations,
sourced from <https://www.bombmanual.com/language.html>). Any other value is rejected with a
`ValidationError` at startup rather than silently falling back to English or writing malformed XML.

|         |         |         |         |      |
| ------- | ------- | ------- | ------- | ---- |
| `en`    | `ar`    | `cs`    | `da`    | `de` |
| `eo`    | `es`    | `fi`    | `fr`    | `he` |
| `hu`    | `it`    | `ja`    | `ko`    | `nb` |
| `nl`    | `pl`    | `pt-BR` | `pt-PT` | `ro` |
| `ru`    | `sv`    | `th`    | `tr`    | `uk` |
| `zh-CN` | `zh-TW` |         |         |      |

## Where the generated file lives

`KtaneSettings.get_dir()` picks the per-OS location:

- **Windows** — `%APPDATA%\..\LocalLow\Steel Crate Games\Keep Talking and Nobody Explodes`
- **macOS** — `~/Library/Application Support/com.steelcrategames.keeptalkingandnobodyexplodes`
- **Linux** — `~/.config/unity3d/Steel Crate Games/Keep Talking and Nobody Explodes`

If a `playerSettings.xml` already exists there and differs from what we'd write, it is backed up to
a timestamped `.bak` next to it before being replaced.
