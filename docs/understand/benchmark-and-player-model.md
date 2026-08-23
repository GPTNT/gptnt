---
title: Benchmark and player model
tags:
  - Model integration
---

# Benchmark and player model

GPTNT measures how configured players collaborate and act in KTANE experiments. A model is one
part of a player. The distinction matters because the same model can participate through different
providers, protocols, processors, settings, or identities.

## Model, player, and service instance

| Term | Meaning in GPTNT |
| ---- | ---------------- |
| Model | The inference target that receives the prepared model input and returns a response. |
| Provider | The client and endpoint configuration used to reach a model. |
| Player configuration | The Hydra configuration that assembles a model, provider, protocol support, processors, limits, identity, and recorder. |
| Player | The assembled participant that turns observations and messages into actions or messages. |
| Player service | One running process that exposes a configured player through Redis RPC. |

Several service processes can use the same player configuration. A run manifest controls their
count. The included test players exercise the pipeline without external provider credentials, so
not every player is backed by a hosted model.

## Roles and access

KTANE defines two collaboration roles:

- The **Defuser** sees and acts on the bomb.
- The **Expert** receives messages and uses the selected manual to advise the Defuser.

A player protocol specifies the role, communication style, manual access, and feedback behaviour
for one side of an experiment. A suite can also use a solo Defuser protocol. Do not infer that
every room always requires two player services.

[Roles, protocols, and capabilities](roles-protocols-and-capabilities.md) explains the supported
pairing modes and the distinction between protocol fields and service matching.

The suite supplies the protocols. The generated experiment specification records the selected
player names and protocols. When the experiment manager creates a running instance, it adds each
service UUID and the capabilities reported by that service.

## Capabilities and identity

Capabilities state properties such as supported modalities and image handling that affect whether
a player can take part in a selected experiment. The runtime heartbeat reports resolved
capabilities. GPTNT copies them into the experiment instance and recorded provenance.

Player identity and capability fingerprints are part of result interpretation. Changing model
settings, configured capabilities, processors, or other identity inputs can produce a different
participant even when the display name remains the same.

The following relationship stays constant across interactive runs:

| Configuration boundary | Runtime boundary | Recorded boundary |
| ---------------------- | ---------------- | ----------------- |
| Model, provider, player profile, and processors | Player service assigned to a protocol role | Player identity, resolved capabilities, steps, and footer |

## Benchmark outcomes

The game state determines the declared experiment outcome: solved, strikeout, or timeout. A model
response alone is not a benchmark result. GPTNT relates the outcome to the suite, mission,
protocols, player identities, capabilities, runtime instance, and provenance captured by the run.

[Trace the experiment hierarchy](experiment-hierarchy.md)
[Add a model](../run-and-submit/add-model.md)
