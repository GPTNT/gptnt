# Lint and verification

Use this guide while fixing lint, formatting, typing, or import-contract failures and during final
verification.

<!-- rule:gptnt:801 -->

- Run the relevant checker against the affected files while editing. After the focused fixes, run
  `mise run format`, which executes `uv run prek run -a` using `.pre-commit-config.yaml`. The final
  pass checks formatting, lint, types, and import contracts with the repository configuration. Use
  `uv run prek run --files path` to include an untracked file in a focused check.

<!-- rule:gptnt:802 -->

- Determine whether a lint failure identifies a local expression, a type problem, or a structural
  problem. Fix that cause. For example, `WPS202` normally requires splitting a module. Add a
  per-file ignore only when the rule does not represent a defect for that file.
