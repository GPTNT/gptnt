---
title: Actions and observations
tags:
  - Python
---

# Actions and observations

Player output models represent the choices a language model can return. Before each model call,
GPTNT prepares game frames and converts a selected location into the game input contract.

## Player output actions

::: gptnt.players.actions
    options:
      heading_level: 3
      show_root_heading: false
      show_source: false
      members:
        - DoNothingAction
        - SendMessageAction
        - InteractGameAction
        - MagicGameAction
        - LotteryGameAction
        - GameInteractionActionType
        - PlayerOutputType

`PlayerOutputType` is the complete supported model-output union. `GameInteractionActionType`
excludes messaging and no-op output.

## Interaction locations

::: gptnt.players.locations
    options:
      heading_level: 3
      show_root_heading: false
      show_source: false
      members:
        - PixelLocation
        - ScaledLocation
        - SingleAlphabetLetter
        - SetOfMarksLocation
        - InteractionLocationMethod
        - CoordinateMode

Set-of-marks locations are a non-negative mark number or one letter. Coordinate output is either
absolute pixels or a normalised integer scale selected by player capabilities.

## Game inputs

::: gptnt.ktane.actions
    options:
      heading_level: 3
      show_root_heading: false
      show_source: false
      members:
        - GameActionType
        - RelativeCoordinate
        - KtaneBaseAction
        - KtaneGameplayInput

## Observations and conversion

::: gptnt.players.observation_handler
    options:
      heading_level: 3
      show_root_heading: false
      show_source: false
      members:
        - Observation
        - ObservationHandler

An `Observation` carries recent PNG frames, an optional segmentation mask, and the processed image
used for set-of-marks output. `ObservationHandler` applies the configured resizing and location
method, then converts interaction output to `KtaneGameplayInput`.

The runtime does not compare suite modality declarations with player capabilities. Validate the
chosen model's image and interaction support before a benchmark run.
