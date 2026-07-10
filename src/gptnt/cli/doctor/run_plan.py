from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from gptnt.cli.checks.result import CheckResult
from gptnt.cli.checks.validation import validate_model_config
from gptnt.cli.run.manifest import RunManifest
from gptnt.common.paths import Paths
from gptnt.experiments.generation.specs import generate_specs
from gptnt.experiments.ledger.resolve import filter_experiments
from gptnt.experiments.spec import ExperimentSpec

RESUME_CHECK = "Resume"
COVERAGE_CHECK = "Roster coverage"


@dataclass(frozen=True)
class _Roster:
    """The resolved roster: config name → player_name, and the reverse for collision detection."""

    config_to_player: dict[str, str]
    player_to_configs: dict[str, list[str]]

    @property
    def player_names(self) -> set[str]:
        """The distinct player names the roster provides."""
        return set(self.player_to_configs)


@dataclass(frozen=True)
class RunPlanResult:
    """The full run-plan outcome.

    The findings, plus the generated specs and the resolved roster (config name -> player_name), so
    callers like `gptnt run` can reuse them without re-resolving or re-generating.

    `remaining_specs` is the WandB-filtered "remaining" specs from the resume step (`None` means
    resume couldn't be determined → run all `specs`), so `run` reuses the one WandB query.
    """

    findings: list[CheckResult]
    specs: list[ExperimentSpec]
    config_to_player: dict[str, str]
    remaining_specs: list[ExperimentSpec] | None = None


def analyze_run_plan(
    manifest: RunManifest,
    config_to_player: dict[str, str | None],
    *,
    specs: list[ExperimentSpec] | None = None,
) -> RunPlanResult:
    """Cross-check the manifest roster against what generation requires, then report resume state.

    `config_to_player` maps each roster *config* name to its resolved `player_name` (or `None` when
    it failed to compose/instantiate). It comes from the SAME `check_players` validation the doctor
    command renders as the matrix, so the matrix and this cross-check can never disagree.

    `specs`, when given, is a pre-generated spec set loaded from disk (the `gptnt run` path): the
    cross-check then reports against exactly what will run, not a fresh regeneration. When `None`
    (standalone `doctor`/`generate`), specs are generated in-memory from the manifest.
    """
    findings: list[CheckResult] = []

    roster = _resolve_roster(manifest, config_to_player, findings)
    anchors = _resolve_anchors(manifest, roster.config_to_player, findings)

    if not roster.player_names:
        # Every roster entry failed to resolve; the ✗ rows above say why, and there is nothing to
        # generate against, so stop here rather than generating with an empty roster.
        return RunPlanResult(findings, [], roster.config_to_player)

    specs = (
        _generate_union(manifest, roster.player_names, anchors, findings)
        if specs is None
        else specs
    )
    appearances = _appearances(specs)

    findings.extend(_unknown_player_findings(roster, anchors, appearances))
    findings.extend(_unused_findings(roster, appearances))
    if not any(finding.status == "fail" for finding in findings):
        # A clean ✓ summary (with the declared spawn counts) only when nothing above is fatal.
        findings.append(_coverage_ok(manifest, roster, appearances, len(specs)))
    resume_row, remaining = _resume(manifest, specs)
    findings.append(resume_row)
    return RunPlanResult(findings, specs, roster.config_to_player, remaining_specs=remaining)


def _resolve_roster(
    manifest: RunManifest, config_to_player: dict[str, str | None], findings: list[CheckResult]
) -> _Roster:
    """Map each roster config to its player_name (from the matrix); flag unresolved/colliding."""
    resolved: dict[str, str] = {}
    player_to_configs: dict[str, list[str]] = defaultdict(list)
    for entry in manifest.players:
        player_name = config_to_player.get(entry.player)
        if player_name is None:
            findings.append(
                CheckResult(
                    f"Roster: {entry.player}",
                    "fail",
                    "config does not resolve to a player_name (it failed to compose/instantiate)",
                    "fix the ✗ for this config in the Models table above",
                )
            )
            continue
        resolved[entry.player] = player_name
        player_to_configs[player_name].append(entry.player)

    for player_name, configs in player_to_configs.items():
        if len(configs) > 1:
            findings.append(
                CheckResult(
                    f"Roster: {player_name}",
                    "fail",
                    f"player_name '{player_name}' is provided by multiple configs: "
                    f"{', '.join(sorted(configs))}",
                    "each player must come from exactly one roster entry",
                )
            )
    return _Roster(resolved, dict(player_to_configs))


def _resolve_anchors(
    manifest: RunManifest, roster_config_to_player: dict[str, str], findings: list[CheckResult]
) -> dict[str, str]:
    """Resolve set anchor *config* names to player names; ✗ on an invalid one.

    Returns a map of anchor field (`best_expert`/`best_defuser`) → player_name for those that
    resolved. An anchor already in the roster reuses its resolved name (no extra validation). An
    unresolved name fails.
    """
    resolved: dict[str, str] = {}
    cache: dict[str, str | None] = {}
    fields = (
        ("best_expert", manifest.anchors.best_expert),
        ("best_defuser", manifest.anchors.best_defuser),
    )
    for field_name, config_name in fields:
        if config_name is None:
            continue
        player_name = _anchor_player_name(config_name, roster_config_to_player, cache)
        if player_name is None:
            findings.append(
                CheckResult(
                    f"Anchor {field_name}",
                    "fail",
                    f"'{config_name}' is not a usable player config",
                    "no player config of that name exists under configs/player/",
                )
            )
            continue
        resolved[field_name] = player_name
    return resolved


def _anchor_player_name(
    config_name: str, roster_config_to_player: dict[str, str], cache: dict[str, str | None]
) -> str | None:
    """Resolve an anchor config name to its player_name, reusing the roster / a per-call cache."""
    if config_name in roster_config_to_player:
        return roster_config_to_player[config_name]
    if config_name in cache:
        return cache[config_name]

    outcome = validate_model_config(config_name)
    player_name = outcome.capabilities.player_name if outcome.capabilities else None
    cache[config_name] = player_name
    return player_name


def _generate_union(
    manifest: RunManifest,
    roster_player_names: set[str],
    anchors: dict[str, str],
    findings: list[CheckResult],
) -> list[ExperimentSpec]:
    """Generate specs for each suite with the roster/anchors injected, deduped into one union.

    `generate_specs` composes ONE `suites=` suite per call, so we iterate the manifest's `suites:`
    list and union the results (deduped by `attempt_name`). A bad suite id or override becomes a ✗
    row naming the suite rather than aborting the whole report.
    """
    roster_override = f"players.all=[{','.join(sorted(roster_player_names))}]"
    anchor_overrides = [
        f"players.{field_name}={player_name}" for field_name, player_name in anchors.items()
    ]
    union: dict[str, ExperimentSpec] = {}
    for suite_name in manifest.suites:
        overrides = [
            f"suites={suite_name}",
            roster_override,
            *anchor_overrides,
            f"attempts_per_mission={manifest.attempts_per_mission}",
        ]
        try:
            specs = generate_specs(overrides)
        except Exception as exc:  # noqa: BLE001 — surface a bad suite/override as a ✗ row
            findings.append(
                CheckResult(
                    f"Generate: {suite_name}",
                    "fail",
                    f"generation failed: {exc}",
                    "check the suite name (run `gptnt list suites`); "
                    "with_best_* matchups need a matching anchor in `anchors:`",
                )
            )
            continue
        for spec in specs:
            union[spec.attempt_name] = spec
    return list(union.values())


def _appearances(specs: list[ExperimentSpec]) -> Counter[str]:
    """Count how many times each player_name appears (as defuser or expert) across the specs."""
    counter: Counter[str] = Counter()
    for spec in specs:
        counter[spec.defuser_name] += 1
        if spec.expert_name is not None:
            counter[spec.expert_name] += 1
    return counter


def _unknown_player_findings(
    roster: _Roster, anchors: dict[str, str], appearances: Counter[str]
) -> list[CheckResult]:
    """Players the run references but the roster does not provide — the silent-stall case (✗)."""
    anchor_by_player = {player_name: field for field, player_name in anchors.items()}
    findings: list[CheckResult] = []
    for player_name in sorted(set(appearances) - roster.player_names):
        hint = f"add a players: entry whose config resolves to '{player_name}'"
        if player_name in anchor_by_player:
            hint = f"it's your {anchor_by_player[player_name]} anchor — {hint}"
        findings.append(
            CheckResult(
                f"Player {player_name}",
                "fail",
                f"required by the run (appears {appearances[player_name]} times) "
                "but no roster entry provides it",
                hint,
            )
        )
    return findings


def _unused_findings(roster: _Roster, appearances: Counter[str]) -> list[CheckResult]:
    """Roster players that no selected experiment ever pairs — a likely mistake (⚠, not fatal).

    `count` is explicit (the user's choice), so we do NOT second-guess how many to spawn; the only
    roster-side smell worth surfacing is a player that is declared but never used.
    """
    findings: list[CheckResult] = []
    for config_name, player_name in roster.config_to_player.items():
        if appearances.get(player_name, 0) == 0:
            findings.append(
                CheckResult(
                    f"Player {config_name}",
                    "warn",
                    "in the roster but no selected experiment uses it",
                    "drop it from players: or select an experiment that pairs it",
                )
            )
    return findings


def _coverage_ok(
    manifest: RunManifest, roster: _Roster, appearances: Counter[str], total_specs: int
) -> CheckResult:
    """The ✓ summary row, naming the declared spawn count per player the run actually uses."""
    appearing = set(appearances)
    spawning = ", ".join(
        f"{entry.player}={entry.count}"
        for entry in manifest.players
        if roster.config_to_player.get(entry.player) in appearing
    )
    detail = f"{len(roster.player_names)} player(s) cover {total_specs} spec(s)"
    if manifest.attempts_per_mission > 1:
        detail = f"{detail} ({manifest.attempts_per_mission} attempts/mission)"
    if spawning:
        detail = f"{detail}; will spawn {spawning}"
    return CheckResult(COVERAGE_CHECK, "pass", detail)


def _resume(
    manifest: RunManifest, specs: list[ExperimentSpec]
) -> tuple[CheckResult, list[ExperimentSpec] | None]:
    """The resume row AND the not-yet-done specs to run.

    The second element is the "remaining" (not-yet-done) specs from the manifest's completion
    source, or `None` when resume could not be determined (errored / no specs) — meaning the caller
    should run all generated specs. This is the SINGLE completion query for the whole run.
    """
    if not specs:
        return (
            CheckResult(RESUME_CHECK, "skip", "no specs were generated, so nothing to resume"),
            None,
        )

    source = manifest.source
    try:
        remaining = filter_experiments(specs, source=source, output_dir=_resume_output_dir())
    except Exception as exc:  # noqa: BLE001 — resume is informational; never block the run
        return (
            CheckResult(
                RESUME_CHECK,
                "warn",
                f"could not determine resume state ({source.value}): {exc}",
                "resume state is unknown; this does not block the run",
            ),
            None,
        )

    done = len(specs) - len(remaining)
    return (
        CheckResult(
            RESUME_CHECK,
            "pass",
            f"{done} of {len(specs)} already done ({source.value}); "
            f"this run would execute {len(remaining)}",
        ),
        remaining,
    )


def _resume_output_dir() -> Path:
    """The recorder output root the local completion check scans (pinned dir, else base)."""
    paths = Paths()
    return paths.experiment_recorder_outputs or paths.experiment_recorder_dir
