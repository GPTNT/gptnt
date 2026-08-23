---
title: Processors
tags:
  - Python
---

# Processors

Processors adapt game images to the dimensions and interaction representation declared by player
capabilities. Hydra player configuration constructs these objects from their public module paths.

## Image dimensions

::: gptnt.common.image_ops
    options:
      heading_level: 3
      show_root_heading: false
      show_source: false
      members:
        - ImageDimensions

## Image resizing

::: gptnt.processors.image_resizer
    options:
      heading_level: 3
      show_root_heading: false
      show_source: false
      members:
        - ImageResizer

`ImageResizer` resizes frames and converts absolute pixel locations to relative game coordinates.

## Set-of-marks processing

::: gptnt.processors.set_of_marks
    options:
      heading_level: 3
      show_root_heading: false
      show_source: false
      members:
        - MaskDrawingParams
        - SetOfMarksHandler

::: gptnt.processors.labels.drawing
    options:
      heading_level: 3
      show_root_heading: false
      show_source: false
      members:
        - AnnotationTextParams
        - AnnotationBackgroundParams

`SetOfMarksHandler` maps visible components to marks and retains the mapping needed to convert a
predicted mark back to a game location. Drawing parameters set the text and background styles used
to render labels on a segmentation mask.

Use the [player configuration reference](../configuration/players.md) for capability fields that
select these processors.
