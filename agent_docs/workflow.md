# Workflow

Read this guide before a change that affects a public boundary, task scope, or verification choice.

## Planning and process

<!-- rule:gptnt:101 -->

- Before changing a public interface, configuration schema, package boundary, shared type, or
  behaviour across several files, write two to four lines describing the options, trade-offs, and
  selected approach.

<!-- rule:gptnt:102 -->

- Keep a change within its stated objective. Preserve unrelated worktree changes and exclude
  opportunistic edits that are not required for the requested outcome.

<!-- rule:gptnt:103 -->

- Ask the user when the available choices change the public interface, stored data, external
  behaviour, or task scope and the request does not determine the choice. Make local implementation
  decisions when they preserve the requested behaviour and remain within scope.

<!-- rule:gptnt:104 -->

- Run targeted tests during development. Use the full suite for final verification when the change
  warrants it. For example, use `uv run pytest tests/cli tests/experiments` while changing those
  areas.
