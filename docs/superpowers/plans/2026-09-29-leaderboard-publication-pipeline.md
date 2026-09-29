# Leaderboard Publication Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a reviewable, `>= 2` randomized-manual leaderboard artifact from merged submission bundles and notify maintainers when action is required.

**Architecture:** `gptnt` owns a deterministic local aggregator because it owns the manifest and Parquet schemas. `GPTNT/submissions` invokes that command after relevant merges and uses a cross-repository credential only to open or update a website PR. `gptnt.github.io` freezes the prior artifact as an archive and treats News and new-model labels as editorial content.

**Tech Stack:** Python 3.13, Pydantic, PyArrow, Cyclopts, pytest, GitHub Actions, GitHub CLI/API, Resend HTTP API, Astro 7.

**Spec:** `docs/superpowers/specs/2026-09-28-leaderboard-publication-design.md`

## Global Constraints

- Select only `multi-self-async` and `multi-self-sync` bundles whose suite revision is `>= 2`.
- Preserve every selected record's exact suite revision and digest in generated JSON.
- Read bundle manifests and `experiments.parquet` directly; do not query W&B or a local DuckDB.
- Never expose the validation or publication credential to untrusted submitted content or a downloaded release subprocess.
- The normal Actions token may read `GPTNT/submissions`; only a separate least-privilege secret may create a website PR.
- The original leaderboard remains a frozen archive; later News posts remain editorial decisions.

## Review Focus

- A revision-1 bundle with the same suite name must not reach the active artifact; test the revision boundary in Task 1.
- A malformed manifest or Parquet payload must stop the aggregator with the bundle path in its error; test that in Task 1.
- Empty eligible input must produce a valid, deterministic artifact rather than stale output; test that in Task 1.
- An unchanged artifact must not create a website PR or an email; test the workflow's diff branch in Task 3.
- `GITHUB_TOKEN` must be present for outer release metadata lookups but absent from the downloaded-release validator; test both environments in Task 2.

---

### Task 1: Deterministic leaderboard artifact command (`gptnt`)

**Files:**
- Create: `src/gptnt/cli/leaderboard/build.py`
- Create: `src/gptnt/cli/leaderboard/__main__.py`
- Create: `tests/cli/test_leaderboard_build.py`
- Modify: `src/gptnt/cli/__main__.py`
- Modify: `docs/reference/files/submission-bundles.md`

**Interfaces:**
- Consumes: `load_submission_bundle(bundle_dir: Path) -> InteractiveBundle | StaticsBundle` and `SubmissionExperiment` from `gptnt.cli.submission`.
- Produces: `build_leaderboard(submissions_dir: Path, *, output: Path) -> None`, exposed as `gptnt leaderboard build <submissions-dir> --output <path>`.
- Produces: JSON with the frozen website contract: schema metadata, selected suite metadata, one entry per interactive bundle, metrics, module breakdown, usage, players, and provenance.

- [ ] **Step 1: Write focused failing artifact tests**

Add tests that create representative interactive bundles with `make_experiment_summary` / `SubmissionExperiment`, then assert that the JSON contains only `multi-self-async` and `multi-self-sync` at revisions 2 and above. Assert the exact metric values for a small mixed solved/timeout/strikeout fixture, module appearances and solved counts, mean role usage, stable ordering, and empty eligible input. Add one malformed-bundle assertion that identifies its directory.

- [ ] **Step 2: Run the new tests to verify failure**

Run: `uv run pytest -q tests/cli/test_leaderboard_build.py`

Expected: FAIL because the leaderboard command and aggregation implementation do not exist.

- [ ] **Step 3: Implement the aggregation service and command**

Create `gptnt.cli.leaderboard.build` as a Cyclopts command module. Discover only flat bundle directories containing `submission.yaml`, load them through `load_submission_bundle`, skip non-interactive and out-of-scope suite revisions, and construct JSON-compatible Pydantic/dictionary output from the typed models. Calculate percentages over the bundle's experiments, calculate `module_breakdown` from `final_bomb_state.modules`, and calculate mean `RunUsage.total_tokens` per role. Sort entries by suite, model display name, and submission id before serializing JSON with a trailing newline. Register the nested `leaderboard` app lazily under the analysis group.

- [ ] **Step 4: Document the command and artifact provenance**

Add the command's input layout, `>= 2` selection rule, and statement that it reads submitted Parquet directly to the submission-bundle reference.

- [ ] **Step 5: Run focused verification**

Run: `uv run pytest -q tests/cli/test_leaderboard_build.py tests/cli/test_submission_validate.py`

Expected: PASS.

- [ ] **Step 6: Commit the aggregator**

```bash
git add src/gptnt/cli/leaderboard src/gptnt/cli/__main__.py tests/cli/test_leaderboard_build.py docs/reference/files/submission-bundles.md
git commit -m "feat: build leaderboard artifacts from submissions"
```

### Task 2: Authenticated published-release validation (`GPTNT/submissions`)

**Files:**
- Modify: `scripts/validate_published_release.py`
- Modify: `.github/workflows/validate.yml`
- Modify: `tests/test_validate_published_release.py`

**Interfaces:**
- Consumes: the workflow-provided `${{ secrets.GITHUB_TOKEN }}`.
- Produces: release/tag requests authenticated with that token; downloaded-release validation subprocesses retain the current credential-free environment.

- [ ] **Step 1: Write a failing validator test**

Inject a request opener or inspect constructed requests so the test asserts `main()` passes `GITHUB_TOKEN` to `fetch_annotated_tag_commit` and `fetch_release`. Retain/add an assertion that `_release_environment()` removes `GITHUB_TOKEN`.

- [ ] **Step 2: Run the validator test to verify failure**

Run: `uv run --with pyyaml==6.0.2 python -m unittest discover -s tests`

Expected: FAIL because `main()` currently passes `token=None`.

- [ ] **Step 3: Use the scoped token at the outer API boundary**

Read `os.environ.get("GITHUB_TOKEN")` once in `main()` and pass it to both tag/release fetches. Add `GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}` only to the workflow's `Validate submissions` step. Do not pass it through `_release_environment()`.

- [ ] **Step 4: Run the validator suite**

Run: `uv run --with pyyaml==6.0.2 python -m unittest discover -s tests`

Expected: PASS.

- [ ] **Step 5: Commit the submissions validation fix**

```bash
git add scripts/validate_published_release.py .github/workflows/validate.yml tests/test_validate_published_release.py
git commit -m "fix: authenticate published release validation"
```

### Task 3: Artifact publication and maintainer notifications (`GPTNT/submissions`)

**Files:**
- Create: `.github/workflows/publish-leaderboard.yml`
- Modify: `.github/workflows/validate.yml`
- Modify: `README.md` or maintainer documentation describing required repository secrets

**Interfaces:**
- Consumes: merged `submissions/**`, `workflow_dispatch`, `WEBSITE_PR_TOKEN`, `RESEND_API_KEY`, `LEADERBOARD_NOTIFICATION_EMAIL`, and `LEADERBOARD_EMAIL_FROM` repository secrets/variables.
- Consumes: released `gptnt` containing `gptnt leaderboard build`.
- Produces: an updated `src/data/leaderboard.generated.json` pull request in `GPTNT/gptnt.github.io` only when the artifact changes.

- [ ] **Step 1: Write a workflow-level acceptance checklist**

In maintainer documentation, record the required least-privilege website PR token, verified Resend sender, email recipient, expected event triggers, and no-change behavior. This is the operational test contract for the workflow.

- [ ] **Step 2: Implement the publication workflow**

Add a workflow triggered by pushes to `main` affecting `submissions/**` and manual dispatch. Check out submissions, install the released/pinned aggregator, run `gptnt leaderboard build` over the checkout, then check out `GPTNT/gptnt.github.io` with `WEBSITE_PR_TOKEN`. Replace only `src/data/leaderboard.generated.json`; create or update a stable data-update PR branch if and only if `git diff --quiet` is false. Configure concurrency so overlapping submission merges coalesce into one update branch.

- [ ] **Step 3: Add action-only Resend notifications**

Send one Resend email after a website PR is opened or updated, and one on validation/publication failure. Include the PR/run URL and requested action. Guard the mail steps so a no-diff run sends no email and email delivery failure is visible rather than silently ignored.

- [ ] **Step 4: Perform a manual-dispatch dry run**

Configure secrets in repository settings, run the workflow with `workflow_dispatch`, and verify that it builds an artifact, opens/updates exactly one website PR, and sends one actionable email. Re-run without bundle changes and verify no additional PR or email.

- [ ] **Step 5: Commit the workflow and documentation**

```bash
git add .github/workflows/publish-leaderboard.yml .github/workflows/validate.yml README.md
git commit -m "ci: publish leaderboard artifacts"
```

### Task 4: One-time website transition (`GPTNT/gptnt.github.io`)

**Files:**
- Create: `src/pages/leaderboard-archive.astro`
- Create: `src/data/leaderboard.original.generated.json`
- Modify: `src/data/leaderboard.generated.json`
- Modify: `src/data/loadLeaderboard.js`
- Modify: `src/data/leaderboard.overlay.json`
- Modify: `src/components/Leaderboard.astro`
- Modify: `src/components/News.astro`

**Interfaces:**
- Consumes: the first `>= 2` artifact from Task 1/Task 3.
- Produces: an active randomized-manual leaderboard in the current format and an archived original-rule-table leaderboard reachable through a quiet link.

- [ ] **Step 1: Copy the current artifact before replacement**

Commit the existing `leaderboard.generated.json` as `leaderboard.original.generated.json`. Build an archive route that reuses the current board rendering against this frozen data and displays precise explanatory copy about original KTANE rule tables and solutions.

Refactor `loadLeaderboard.js` so its projection function accepts an explicit generated artifact and overlay; keep the existing default export for the active board. The archive page must call that projection with the frozen artifact rather than import active-board data.

- [ ] **Step 2: Add the unobtrusive archive link and active-board editorial overlay**

Link to the archive from the active leaderboard's supporting copy. Fill `overlay.newModels` with display names present in the first new artifact but absent from the frozen artifact; preserve baseline and diagnostics data.

- [ ] **Step 3: Add the initial News item**

Add one date-stamped News entry introducing the randomized-manual leaderboard, the new results, and the archive. Do not build a mechanism that creates later News entries from every data update.

- [ ] **Step 4: Verify the website transition**

Run: `pnpm build`

Expected: PASS. Run `pnpm dev`, inspect `/` and `/leaderboard-archive/`, and confirm the archive and active rows differ as expected.

- [ ] **Step 5: Commit the website transition**

```bash
git add src/pages/leaderboard-archive.astro src/data/leaderboard.original.generated.json src/data/leaderboard.generated.json src/data/loadLeaderboard.js src/data/leaderboard.overlay.json src/components/Leaderboard.astro src/components/News.astro
git commit -m "feat: publish randomized-manual leaderboard"
```

### Task 5: End-to-end backfill and release verification

**Files:**
- Modify: the three repositories only as produced by Tasks 1–4.

**Interfaces:**
- Consumes: the merged `>= 2` submissions currently on `GPTNT/submissions:main`.
- Produces: the first reviewed website pull request and a repeatable automation path.

- [ ] **Step 1: Release the aggregator before the publication workflow references it**

Publish the `gptnt` version containing `leaderboard build`, pin that released version in the submissions workflow, and record the version in the workflow file.

- [ ] **Step 2: Run the first manual backfill**

Use `workflow_dispatch` after the workflow is merged. Confirm the produced artifact contains every eligible revision-2-or-later bundle and no revision-1 bundle.

- [ ] **Step 3: Review and merge the website transition/data PR**

Confirm the artifact, archive link, `NEW` labels, and initial News item. Merge only after the website build succeeds.

- [ ] **Step 4: Confirm steady-state behavior**

Merge or use a controlled future submission, then confirm one submissions workflow run updates the existing website-data PR and sends one email. Confirm an unchanged run leaves no new PR/comment/email.
