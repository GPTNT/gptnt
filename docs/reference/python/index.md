---
title: Python interfaces
tags:
  - Python
---

# Python interfaces

These pages group selected local objects used by player integrations and Hydra configuration. They
do not document every importable implementation object.

| Interface group | Objects |
| --------------- | ------- |
| [Player interfaces](player-interfaces.md){data-preview} | Player identity, capabilities, protocol, specification, prediction, and call results |
| [Actions and observations](actions-and-observations.md){data-preview} | Model output actions, game inputs, locations, observation payloads, and conversion |
| [Processors](processors.md){data-preview} | Image sizing, resizing, and set-of-marks configuration |
| [Experiment generation](experiment-generation.md){data-preview} | Suites, pairings, missions, specifications, and frozen snapshots |
| [Completion and provenance](completion-and-provenance.md){data-preview} | Completion ledgers, release identity, and protected-content state |

!!! info "Support boundary"
    Objects listed on these pages are the selected Python reference surface for v2. Nested helper
    modules and unlisted names remain implementation details even when Python can import them.

The `Conversation` re-export remains a lower-level player-loop object. Its construction contract is
not part of this selected surface.
