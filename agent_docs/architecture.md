# Architecture

Use this guide when adding a module, class, helper, or public interface, and when moving code
between packages.

## Ownership and reuse

<!-- rule:gptnt:301 -->

- Keep one implementation for each concept. Put the implementation in the package that owns the
  behaviour and import it at other call sites. Before adding similar logic, search for an existing
  implementation that can serve both callers. Use one parametrised implementation when commands or
  input forms differ only by data. Keep separate implementations when they validate different
  concepts, produce different side effects, or are expected to change independently.

## Code shape

<!-- rule:gptnt:302 -->

- Keep related types in one module while they form one feature and can be understood together. Split
  the module when the types have separate consumers or the file no longer supports one downward
  reading. `common/duckdb.py` keeps its related DuckDB conversion types together.

<!-- rule:gptnt:303 -->

- Construct a value at its call site when construction is direct and has one consumer. Add a factory
  when construction branches on its inputs, enforces a shared invariant, or is reused by several
  callers.

<!-- rule:gptnt:304 -->

- Check the standard library and installed dependencies before writing a helper. Wrap an existing
  function only when the wrapper adds a project-specific default, validation, error conversion, or
  interface. For example, use `textwrap.shorten` to cap text and `textwrap.dedent` to remove
  template indentation.

<!-- rule:gptnt:305 -->

- Give a value one shared definition when several processes or packages must agree on it. Import a
  shared settings type when both sides can depend on the same module. When package or deployment
  boundaries prevent that import, add a test that fixes the value on both sides. Runtime settings
  shared across services live in `src/gptnt/common/runtime_settings.py`.

<!-- rule:gptnt:306 -->

- Delete an implementation in the same change that replaces it. Retain the earlier path only when
  the task requires compatibility with an existing caller or stored format, and document that
  requirement.

<!-- rule:gptnt:307 -->

- Inline a wrapper or single-use helper that only forwards arguments, returns one attribute, or
  renames a short expression. This includes a private helper used once whose body only sorts,
  filters, or comprehends one directly available collection. Keep the helper when it defines a
  public API or enforces an invariant or policy. Keep it when its body contains logic that benefits
  from a name or performs several access steps. Keep it when it caches work or keeps its caller at
  one abstraction level. Keep it when it converts errors or applies project-specific behaviour. Do
  not add a wrapper before it has a caller.

<!-- rule:gptnt:308 -->

- Keep a helper, constant, compiled regular expression, or reusable adapter at the narrowest scope
  that supports its use. A value used by one block may stay in that function. A value used by a
  signature, decorator, class, or several functions belongs at module scope.

  Keep a function-specific literal default in its keyword-only parameter when no other code needs
  to name it. Define a module constant when several functions share the value, configuration or
  tests refer to it directly, or its name explains a domain threshold that the literal does not.
  Values calculated from runtime state stay in the function body.

<!-- rule:gptnt:309 -->

- Move operations shared by sibling branches outside the branches. Keep only the differing
  conditions and values inside each branch. Do not combine branches when doing so obscures different
  side effects or error handling.

<!-- rule:gptnt:311 -->

- Store domain data on the domain object or service that defines it. Do not add data to a report or
  presentation object only to let another caller avoid recomputation. Add caching at the point that
  performs the calculation when measurement shows that recomputation matters.

## Naming

<!-- rule:gptnt:312 -->

- Name a function for the result or operation callers use. Do not include an implementation detail
  that can change without changing the interface. For example, `get_toolset()` remains accurate if
  the toolset later comes from somewhere other than a file. Rename the function when its behaviour,
  scope, or return value changes enough that the existing name becomes inaccurate, and update its
  callers and documentation in the same change.

<!-- rule:gptnt:313 -->

- Give a value enough context to distinguish it from similar values in the same scope. Prefer
  `toolset_id` to `id` when several identifiers are present. Do not append a type name such as
  `_dict` when the annotation already communicates the type and the suffix does not add domain
  meaning.

<!-- rule:gptnt:314 -->

- Do not repeat a class's context in every member name. `ToolConfig.description` already identifies
  the description as belonging to the tool configuration. A name imported and used without its
  module or owner must remain self-contained; `MessageHistory` remains clear at an import site where
  `History` may not.

<!-- rule:gptnt:327 -->

- Name a module for the domain its types describe rather than for holding types. `resolution.py`
  holds the resolved-document types and `manifest.py` holds the manifest. Do not name a module
  `models`, `types`, `base`, or `core`. Those names state nothing about the contents. `gptnt:312`
  applies the same test to function names.

<!-- rule:gptnt:328 -->

- Keep one verb for one operation along a call chain. A public `save_*` that calls `_write_*` which
  calls a third verb makes the reader check whether three different things happen. Use `save_` for
  writing to a store.

## Package boundaries

<!-- rule:gptnt:316 -->

- Define files in reading order: imports, constants, types, helpers, and then their callers. Put a
  module-level helper above the class or function that calls it. Split a file when its definitions
  cannot be followed in one downward reading.

<!-- rule:gptnt:317 -->

- Do not import an underscore-prefixed symbol or module from another package. Promote the required
  interface to that package's public API. Tests may import private symbols when they directly test
  the private implementation.

<!-- rule:gptnt:318 -->

- Put code in `common` only when several packages need it and no domain package owns it. Domain
  logic stays in its domain package. Presentation helpers stay in the CLI or application package
  that directly uses them.

<!-- rule:gptnt:319 -->

- Defer an import inside the feature that requires it when importing the dependency at module load
  would prevent CLI `--help` from rendering or require an optional package on code paths that do not
  use it. `test_lazy_imports` checks the CLI requirement. W&B support, for example, is provided
  through the `gptnt[wandb]` extra.

## API design

<!-- rule:gptnt:320 -->

- Prefix an implementation detail with `_` and exclude it from the documented package API. Apply the
  same convention to a module used only inside its package, such as `_bundle.py` or `_checks.py`.
  Sibling modules may import that module. Other packages must use the package's public API. A public
  name represents an interface callers may depend on.

<!-- rule:gptnt:321 -->

- Re-export the public package API from `__init__.py` and list those names in `__all__` when callers
  need a stable package-level import. Leave `__init__.py` empty when the package has no public names
  to expose. `experiments.ledger` and `interactive.orchestration` provide examples. Do not re-export
  names from an underscore-prefixed module as part of the package's public API.

<!-- rule:gptnt:322 -->

- Use an instance method when an operation reads or changes instance state or participates in
  polymorphism. Use a module-level function when the operation does not require instance state. Put
  logic shared by several classes in a private module-level helper rather than duplicating it.

<!-- rule:gptnt:324 -->

- Give a project-defined function at most one obvious primary positional parameter. Put other
  parameters after `*` when their order is not conventional, when two parameters have similar types,
  or when the call is clearer with names. Required parameters may be keyword-only. Keep several
  positional parameters only when their order is established by a protocol or forms a conventional
  unit such as `host, port`.

  Use all keyword-only parameters when the function has no primary input, as with a calculation that
  combines several independent values. Methods exclude `self` and `cls` from this decision. Dunder
  methods, callbacks, framework hooks, and protocol implementations keep the signature required by
  their interface.

  For example, use `resolve(source, *, output_dir)` for one primary input and one keyword-only
  control. Use `truncate(*, entries, measured_tokens, token_limit)` when every input has an
  independent meaning. A conventional pair may remain positional, as in `connect(host, port, *,
timeout=...)`.

<!-- rule:gptnt:325 -->

- Declare `__all__` only in `__init__.py`, and only when the package publishes a stable
  package-level import. Do not declare it in any other module. Every `__all__` is a second list of
  names that has to change whenever those names change.
