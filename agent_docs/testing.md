# Testing

Use this guide when changing a test, fixture, factory, case set, harness, or any file under
`tests/`.

## Test layout

The test tree follows the source tree. A module at `src/gptnt/<package>/foo.py` is tested at
`tests/<package>/test_foo.py`. The remaining `tests/core/` paths come from the former
`packages/gptnt-core` layout and should move to paths that match the current source package when
those tests are changed.

Shared test infrastructure has these locations:

- `_cases/` contains pytest-cases classes and `param_fixtures`. Use a cases class when a test must
  run over a named, closed set of domain configurations.
- `_factories/` contains `make_*` functions that construct one valid composite object with useful
  defaults, such as an experiment specification or summary.
- `_harness/` contains substitutes for external dependencies, currently the game binary and Redis.
  The application services run unchanged against those substitutes.
- `_data/` contains binary fixtures such as screenshots and segmentation masks. Read them through
  the `fixture_path` fixture.
- `_cli_runner.py` contains `invoke_cli`, which runs CLI parsing and returns the exit code and
  captured output.

The root `tests/conftest.py` contains suite-wide fixtures and the `_cases` plugin registration. A
package-specific conftest contains fixtures for that package only.

## Choosing test infrastructure

<!-- rule:gptnt:601 -->

- Exercise the domain types and implementation used by the application. Use a `make_*` factory when
  one test needs a valid composite object and the object's exact construction is not under test.
  Construct a flat object such as `PlayerProtocol` or `PlayerCapabilities` directly when its
  constructor and defaults already make the setup clear.

  Use a cases class when the set of variants is itself part of the test. The cases class defines the
  variants and any rules that exclude invalid combinations. Keep its `param_fixture` beside the
  cases class.

  Use the harness when the test concerns communication among services or behaviour across a
  process, Redis, or game-binary boundary. Replace an external dependency or a narrow
  nondeterministic boundary when the test requires control over it. Do not replace the application
  service or other code whose behaviour the test is intended to verify.

  Use a fixture when setup is shared or requires teardown, or when it injects a dependency. Do not
  wrap a one-line construction in a fixture only to move it out of the test.

## Test rules

<!-- rule:gptnt:602 -->

- Make each test observe a behaviour that could fail. Assert the returned value, rendered content,
  state change, raised error, or external call that represents that behaviour. A regression test
  whose requirement is "does not raise" should also assert the state or result produced after the
  operation when such an observation exists.

<!-- rule:gptnt:603 -->

- Test a CLI command through `invoke_cli` when the behaviour includes argument parsing, conversion,
  validation, output, or exit status. Call the command function or pipeline directly when the test
  targets internal domain behaviour or needs to assert a Python exception below the CLI boundary.

<!-- rule:gptnt:604 -->

- Do not add a test for a value that only passes unchanged through typed call sites. Test the
  validation, calculation, or side effect at the receiving boundary. Add an integration test when
  serialization, process communication, dependency injection, or configuration composition could
  alter the value in transit.

<!-- rule:gptnt:605 -->

- Remove a test when another test already exercises the same behaviour at the same boundary, or when
  the behaviour no longer exists. When a conditional branch can occur in a supported environment,
  add a test that supplies the input needed to run that branch. Use `# pragma: no cover` only when
  the branch cannot execute in the supported test environments, such as a platform-specific guard.

<!-- rule:gptnt:606 -->

- Protect a behaviour-preserving refactor with an observable-output or golden-file test when several
  implementations must continue to produce the same value. Pin output such as `(revision, digest)`
  through the public loading and construction path. Remove a temporary refactor guard after the new
  structure is established if another test already covers the behaviour.

<!-- rule:gptnt:607 -->

- Remove a factory, fixture, or registration when it has no caller. Search for consumers before
  adding or deleting shared test infrastructure.

<!-- rule:gptnt:608 -->

- Use `integration` for tests that run application services against fake Redis or the fake game
  binary. Use `slow` for tests whose runtime warrants separate selection. Use `requires_game` for
  tests that require the installed game binary and are skipped in CI.

## Test-value pass before completion

Apply this pass before presenting a change that adds, modifies, or removes tests as ready to
commit. Review the tests changed by the task and the directly related tests in the same modules.
Do not expand the pass into unrelated packages.

<!-- rule:gptnt:609 -->

- If a weak test is the only test protecting a behavior, strengthen it before removing it.

<!-- rule:gptnt:610 -->

- Remove tests that only confirm that a module imports, a command or feature exists, a parameter or
  schema field is present, or a declared default is unchanged. Remove assertions validated by the
  type checker or by reading the model declaration. Keep a test when construction, validation,
  configuration composition, serialization across a process boundary, or another runtime operation
  can transform or reject the value.

<!-- rule:gptnt:611 -->

- Test contracts owned by `gptnt`, not contracts owned by a dependency. Do not reproduce an
  inference provider, Discord, HTTP service, Pydantic, or serialization library's object and error
  matrix to show that the dependency follows its own API. Do not recreate external-provider
  internals. Use the smallest fake input needed to test the translation or policy we own.

<!-- rule:gptnt:612 -->

- Keep one focused test per behavior. Remove duplicates, unnecessary parameter matrices, and
  snapshots of third-party output.

<!-- rule:gptnt:613 -->

- Reduce parameter matrices unless each case selects a distinct project branch or policy. Use one
  representative input for pass-through behaviour. Add cases for the boundaries and error
  combinations implemented by `gptnt`; do not multiply those cases across protocols, models, or
  provider errors when the same handler processes every combination.

<!-- rule:gptnt:614 -->

- After removing tests, remove fixtures, cases, fake models, imports, data files, and plugin
  registrations that have no remaining consumer. Search the entire test tree before deleting shared
  infrastructure. Keep reusable harnesses that still support another behavioural or integration
  test.

<!-- rule:gptnt:615 -->

- Do not delete the only test of supported behavior merely because it is awkward. Strengthen or
  simplify it first.

<!-- rule:gptnt:616 -->

- Before deleting a test, confirm another test covers the behavior or strengthen it first.

<!-- rule:gptnt:617 -->

- Run the affected tests after the reduction, then run the final checks required by `gptnt:104` and
  `gptnt:801`. When coverage is relevant, measure production code with a fixed source denominator,
  for example `uv run pytest --cov=src/gptnt`. Treat a coverage decrease as a prompt to inspect the
  newly uncovered lines, not as a reason to restore tests that only import code or repeat a
  dependency contract.

<!-- rule:gptnt:618 -->

- Run integration tests separately when their fixtures or process lifecycle
  make a combined run unreliable, and report that separation with the verification results.
