---
title: Player interfaces
tags:
  - Python
---

# Player interfaces

The specification models define recorded player identity and behaviour. Prediction interfaces
connect a configured Pydantic AI agent to the player loop.

## Specifications

::: gptnt.players.specification
    options:
      heading_level: 3
      show_root_heading: false
      show_source: false
      members:
        - PlayerIdentity
        - PlayerCapabilities
        - PlayerProtocol
        - PlayerSpec

`PlayerIdentity` is submission attribution. `PlayerCapabilities` affects prompts, parsing, image
handling, and the participant fingerprint. `PlayerProtocol` assigns a role and communication
contract for an experiment. `PlayerSpec` is the resolved process specification consumed by a
player service.

## Prediction

::: gptnt.players.action_predictor
    options:
      heading_level: 3
      show_root_heading: false
      show_source: false
      members:
        - ActionPredictor

`ActionPredictor` makes the configured agent call and returns a GPTNT result wrapper. Provider model
objects, model settings, usage limits, and output modes follow the
[Pydantic AI API](https://ai.pydantic.dev/api/).

## Call results

::: gptnt.players.result
    options:
      heading_level: 3
      show_root_heading: false
      show_source: false
      members:
        - AgentCallResult
        - DispatchedAgentCallResult

`AgentCallResult` pairs parsed model output with response metadata. The dispatched variant also
stores the action dispatch result.

For configuration choices, use [Add a model](../../running/add-new-player.md). For the relationship
between these models, use [Roles, protocols, and capabilities](../../understand/roles-protocols-and-capabilities.md).
