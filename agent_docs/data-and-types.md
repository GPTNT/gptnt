# Data and types

Use this guide when defining a model, configuration type, specification, dataclass, type alias, or
function signature.

## Data models

<!-- rule:gptnt:401 -->

- Use a dataclass or Pydantic model when defining a class whose primary purpose is to hold data. Use
  a `NamedTuple` for the small positional records described in `gptnt:419`. A new data class should
  represent a distinct domain value rather than duplicate an existing model, dataclass, or mapping.

<!-- rule:gptnt:402 -->

- Use a Pydantic model when data crosses a serialisation, configuration, environment, or validation
  boundary. Keep compatibility parsing at the external boundary and pass a validated model into the
  rest of the application. Use a standard-library dataclass for an internal service or result that
  does not cross such a boundary, and make an immutable result a frozen dataclass.

  `src/gptnt/experiments/spec.py` contains the experiment configuration models; `ActionPredictor`
  and `CheckResult` are examples of the two dataclass forms.

<!-- rule:gptnt:403 -->

- Use a property or computed field when a derived value depends only on one model's fields and forms
  part of that model's interface. Use a function when the calculation combines objects, accepts
  external inputs, or should remain outside the model API. `ExperimentSpec.experiment_name` is
  derived only from its `ExperimentSpec` instance, and `RuntimeSettings.em_base_url` derives from
  the settings model's host and port. Keep validation and instance-derived behaviour with the model
  instead of introducing a second object that operates on the same fields.

<!-- rule:gptnt:404 -->

- Enforce an invariant among fields with `@model_validator(mode="after")` and return `Self`. This
  ensures that every constructed model satisfies the invariant. Validate in a caller instead when
  the condition depends on state that is not part of the model.

<!-- rule:gptnt:405 -->

- Freeze specifications and configurations and reject unknown fields with
  `ConfigDict(frozen=True, extra="forbid")` or `class X(BaseModel, frozen=True)`. If an external
  format permits additional fields, isolate that format at the boundary rather than weakening the
  internal model.

<!-- rule:gptnt:406 -->

- Use `@dataclass(kw_only=True)` when a dataclass has more than one field with an independent
  meaning or when a positional call would not identify what each value means. Positional fields are
  appropriate for a small value whose order is conventional and forms part of its interface.
  Keyword-only fields allow fields to be reordered or extended without changing existing calls.

<!-- rule:gptnt:407 -->

- Return a new collection from a transform unless the function explicitly promises mutation or
  measurement shows that copying is a problem. Name a mutating operation `update_*` or `*_inplace`
  so callers can identify the state change.

<!-- rule:gptnt:408 -->

- Give a frozen model used as a dictionary key or set member an explicit `@override __hash__`.
  Expose persistent grouping or comparison identity through a deterministic `fingerprint` or
  `stable_digest` property. `PlayerCapabilities.fingerprint` is the project example.

<!-- rule:gptnt:409 -->

- Serialize one Pydantic model with `model_dump()`. Use a JSON-mode `TypeAdapter` for collections or
  when an external SDK requires JSON-compatible primitives. Do not assemble a dictionary manually
  when the model already defines the serialised fields.

<!-- rule:gptnt:410 -->

- Use `@cached_property` when a computed attribute is expensive, may be read more than once, and
  does not change during the instance's lifetime. Use a normal property for inexpensive work or
  values that must reflect later state changes.

## Field documentation and schema metadata

<!-- rule:gptnt:420 -->

- Explain a model field with a string literal under the field. Use `Field(description=...)` only
  when the description must reach an external schema. Do not use both forms in one class.

## Type system

<!-- rule:gptnt:411 -->

- Annotate a value with the most specific type that represents every runtime value it may hold. Use
  a concrete model, `Literal`, `Protocol`, or `TypedDict` where appropriate. Use `Any`, bare
  `object`, or an untyped dictionary only at a boundary whose shape is determined at runtime, and
  document why a narrower type is unavailable.

<!-- rule:gptnt:412 -->

- Use `isinstance()` when the runtime object has a class that represents the distinction and the
  check should narrow its type. Use a discriminator field when data is still a serialised mapping
  and no runtime class exists. Do not compare `type(obj).__name__` or use reflective attribute
  checks as a substitute for an available type.

<!-- rule:gptnt:413 -->

- Represent a closed set of strings with a PEP 695 `Literal` alias. Use plain `str` when values are
  intentionally open-ended or supplied by an external system. `type PlayerRole =
Literal["defuser", "expert"]` represents the closed player-role set.

<!-- rule:gptnt:414 -->

- Make a signature represent the values that can reach it. Remove `| None` when preceding control
  flow guarantees a value. Include `None` when absence is an accepted input or return state.

<!-- rule:gptnt:415 -->

- Fix a type error by correcting the annotation, generic, or control-flow narrowing. When a checker
  limitation prevents it from inferring a type established by runtime validation or control flow,
  use `cast()` or a suppression and state the runtime condition that makes the operation safe. A
  cast must not conceal a structural mismatch.

<!-- rule:gptnt:416 -->

- Create a type alias for a repeated shape or a type expression whose complexity obscures the
  surrounding signature. Three or more union branches normally justify an alias. Keep a simple,
  single-use annotation inline.

<!-- rule:gptnt:417 -->

- Use `match` and `case` for a `Literal` union when the branches implement distinct behaviour and
  exhaustiveness matters. A short `if` remains appropriate for one condition or two branches whose
  exhaustiveness is already apparent. `ExperimentSpec.get_player_protocol` demonstrates the
  exhaustive case.

<!-- rule:gptnt:418 -->

- Access a statically known field directly. Do not loop over field-name strings with `getattr()` or
  `setattr()` when the fields are part of the declared type. Reflection remains appropriate at a
  boundary whose field names are supplied at runtime.

<!-- rule:gptnt:419 -->

- Use `NamedTuple` for a small fixed record that code constructs and unpacks positionally. Use
  `TypedDict` when the value must retain mapping behaviour, such as JSON data or keyword arguments.
  Use a dataclass or Pydantic model when the value needs methods, validation, defaults, or a larger
  interface.
