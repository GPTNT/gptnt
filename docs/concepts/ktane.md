---
title: Controlling KTANE
---

[Keep Talking and Nobody Explodes](https://keeptalkinggame.com/) (KTANE) is a huge part of this benchmark. Therefore, we need to be able to control it, instrument it, and run it in a way that allows us to see exactly what is happening in the game without having to look at the game.

## Controlling the game

The settings for KTANE can be controlled by an XML file. We use this to set various settings.
The game's `playerSettings.xml` is written into the per-user config directory every time an instance starts (via `KtaneSettings.create_settings_files()`).
We expose the ability to set some of these settings through environment variables.

!!! warning
You should not edit the generated `playerSettings.xml` file directly. It is overwritten every time the game starts. Instead, set the environment variables and let `KtaneSettings` render the XML file.

### Config directory for the generated file

`KtaneSettings.get_dir()` picks the per-OS location:

- **Windows** — `%APPDATA%\..\LocalLow\Steel Crate Games\Keep Talking and Nobody Explodes`
- **macOS** — `~/Library/Application Support/com.steelcrategames.keeptalkingandnobodyexplodes`
- **Linux** — `~/.config/unity3d/Steel Crate Games/Keep Talking and Nobody Explodes`

If a `playerSettings.xml` already exists there and differs from what we'd write, it is backed up to a timestamped `.bak` next to it before being replaced.

### What can you control?

All variables use the `KTANE_` prefix. Defaults live on the `KtaneSettings` type
(`src/gptnt/ktane/game_settings.py`); the template is `src/gptnt/ktane/playerSettings.xml`.

#### Sound

By default, we disable all the sound in the game since it's not used by the models. But if you want to hear the game, you can set the music and SFX volumes to non-zero values.

| Setting      | Env var              | Default | XML element     | Notes         |
| ------------ | -------------------- | ------- | --------------- | ------------- |
| Music volume | `KTANE_MUSIC_VOLUME` | `0`     | `<MusicVolume>` | integer 0–100 |
| SFX volume   | `KTANE_SFX_VOLUME`   | `0`     | `<SFXVolume>`   | integer 0–100 |

!!! note
Volumes outside `0–100` are rejected with a `ValidationError` at startup rather than writing an invalid file.

#### Resolution

As mentioned "[elsewhere]" (todo), models are given a fixed-size image of the game window. As a result, we don't need to run the game at a high resolution because then we would need to resize it down to the fixed size anyway. So we run the game at a low resolution by default. But if you want to see it, you can set the width and height to something larger.

| Setting       | Env var             | Default | Notes                          |
| ------------- | ------------------- | ------- | ------------------------------ |
| Window width  | `KTANE_GAME_WIDTH`  | `640`   | also exported to `GAME_WIDTH`  |
| Window height | `KTANE_GAME_HEIGHT` | `480`   | also exported to `GAME_HEIGHT` |

!!! note
We re-export the width and height to `GAME_WIDTH` and `GAME_HEIGHT` because this is what the mod itself uses to set the window size. But we just require you to set `KTANE_GAME_WIDTH` and `KTANE_GAME_HEIGHT`, and we will set the other two for you.

#### Language

If you want to change the language of the game, you can set the `KTANE_LANGUAGE_CODE` environment variable. The value must be one of the codes KTANE ships (English plus 26 translations, sourced from <https://www.bombmanual.com/language.html>). Any other value is rejected with a `ValidationError` at startup rather than silently falling back to English or writing malformed XML.

| Codes   |         |         |         |      |
| ------- | ------- | ------- | ------- | ---- |
| `en`    | `ar`    | `cs`    | `da`    | `de` |
| `eo`    | `es`    | `fi`    | `fr`    | `he` |
| `hu`    | `it`    | `ja`    | `ko`    | `nb` |
| `nl`    | `pl`    | `pt-BR` | `pt-PT` | `ro` |
| `ru`    | `sv`    | `th`    | `tr`    | `uk` |
| `zh-CN` | `zh-TW` |         |         |      |

#### Game speed

If you want to make the game run faster or slower, you can set the `KTANE_GAME_SPEED` environment variable. The value is a multiplier, where `1` is normal speed, `2` is double speed, `0.5` is half speed, etc.

!!! warning
This is mainly useful when you're doing loads of debugging. Make sure you don't set this when you run the experiments though!
