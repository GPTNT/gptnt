# Errors and results

Use this guide when raising, catching, converting, or reporting a failure, and when acquiring a
resource that must be released.

## Error handling

<!-- rule:gptnt:501 -->

- Keep one error convention within each layer. Domain and library code either returns its declared
  result type or raises an exception. The CLI converts a failure into user-facing output and an exit
  status. At the CLI boundary, print the failure in red and re-raise when Cyclopts is responsible
  for producing the non-zero exit status. Do not print an error in a lower layer that will also be
  reported by the CLI.

<!-- rule:gptnt:502 -->

- Return a result object for an expected check whose failure must be displayed, aggregated, or
  accompanied by a corrective `hint`. A missing binary, occupied port, or invalid configured name in
  `doctor` is represented by `CheckResult(name, status, detail, hint)`. Raise an exception when the
  caller cannot continue and does not need to aggregate the failure with other results.

<!-- rule:gptnt:503 -->

- Catch the specific exception at the point that can recover, translate it, add required context, or
  record it as a result. Let the exception continue when the current layer cannot take one of those
  actions.

<!-- rule:gptnt:504 -->

- Define a domain exception when a caller must distinguish that failure from other exceptions or
  when the external exception must not form part of the package interface. Let a clear existing
  exception propagate when callers do not handle it differently. Convert an external exception with
  `raise ... from error` so the original cause remains available. Log the failure where it stops;
  do not log it before re-raising to a caller that will report it again. `GameNotFoundError`
  identifies a failure callers distinguish in `src/gptnt/ktane/executable.py`.

<!-- rule:gptnt:505 -->

- Release a spawned process, Redis connection, file handle, or other acquired resource on every exit
  path. Use a context manager when the resource supports one and `try/finally` otherwise.

<!-- rule:gptnt:506 -->

- Use `assert` for type narrowing or an internal invariant that indicates an implementation defect
  if violated. Do not use it for user input or an expected runtime failure because Python may remove
  assertions in optimized mode. `S101` is disabled to permit internal invariant checks.

<!-- rule:gptnt:507 -->

- Validate input before starting an expensive or state-changing operation when validation does not
  depend on that operation. Report the invalid value and the condition it violates.

<!-- rule:gptnt:508 -->

- Reject an explicit configuration conflict. Use a fallback only when the value was absent,
  automatically inferred, or documented as optional. State the selected fallback when users need it
  to understand the resulting behaviour.

<!-- rule:gptnt:509 -->

- Use `except Exception` only to isolate one unit of a batch whose remaining units must continue.
  Keep the `try` block to that unit, record or log the caught exception, and add `# noqa: BLE001`
  with the isolation reason. The doctor checks use this pattern so one player configuration does not
  stop the remaining checks.

<!-- rule:gptnt:510 -->

- Check the response of a request even when no later code uses its body. For an HTTP response, call
  `raise_for_status()` before treating the request as successful.

<!-- rule:gptnt:511 -->

- Let Pydantic report schema validation errors with their field locations. Catch `ValidationError`
  only when the boundary must combine it with other results or convert it to a documented external
  error format. Do not add a field or model validator only to replace Pydantic's missing-field,
  type, or extra-field error with another message. Use a `mode="before"` validator only when an
  operation must precede field validation, such as transforming an explicitly supported external
  representation or applying a validation-context loading policy, and the declared field types,
  aliases, and other schema features cannot express it. Remove compatibility transformations when
  support for their input representation ends.

<!-- rule:gptnt:512 -->

- Write an exception message directly in the `raise`. Use `!r` for identifiers and user-supplied
  values when repr quoting distinguishes empty strings or surrounding whitespace, as in
  `f"Tool {name!r}"`. The `EM` and `TRY003` rules are disabled.

<!-- rule:gptnt:513 -->

- Let an operation raise its own failure when that exception already identifies the value and the
  condition. Do not check that a file exists before opening it, that a key is present before
  indexing it, or that a parameter is not `None` when its annotation already excludes `None`. Add a
  guard when the native failure would be misleading or would not explain the domain rule being
  violated. Also add one when the check must precede an expensive or state-changing operation, or
  when callers distinguish the resulting exception type. `Path.read_text` reports the missing path in
  its message. `gptnt:214` states the same convention for mappings.

<!-- rule:gptnt:514 -->

- Subclass the builtin exception whose meaning matches the failure. A missing game binary raises
  `GameNotFoundError(FileNotFoundError)` and an unknown mark identifier raises
  `InvalidMarkLocationError(KeyError)`. Use `Exception` as the base when no builtin describes the
  failure. Do not use `RuntimeError` as a default base for a failure a builtin already describes.
  Callers depend on the builtin base: `src/gptnt/cli/checks/game.py` catches `OSError` to cover both
  executable errors.

<!-- rule:gptnt:515 -->

- Raise a builtin exception when its message would state the same information as a domain exception.
  Define a domain exception only when a caller catches it by type. `GameNotFoundError` qualifies
  because `src/gptnt/cli/checks/game.py` catches it. An exception that no caller catches does not.

<!-- rule:gptnt:516 -->

- Trust the types and assumptions the code already establishes. Validate external input once, at the
  highest entry point that accepts it, and do not repeat that validation in the functions it calls.
  An internal function given an empty collection or an unexpected type fails where the value is
  used, and that is the correct report. `gptnt:513` covers the related case of a guard that repeats
  a failure the operation already produces.
