"""Build the website leaderboard artifact from a submissions checkout."""

import json
from collections import defaultdict
from pathlib import Path
from typing import Annotated, Any

import yaml
from cyclopts import Parameter

from gptnt.cli.submission._bundle import InteractiveBundle, load_submission_bundle
from gptnt.cli.submission._schema import SubmissionExperiment, SubmissionPlayer

_ELIGIBLE_SUITES = frozenset(("multi-self-async", "multi-self-sync"))
_MINIMUM_SUITE_REVISION = 2
_ZERO_PERCENT = float()


def _submission_directories(submissions_dir: Path) -> list[Path]:
    """Return the flat bundle directories in a submissions checkout or directory."""
    bundles_root = submissions_dir / "submissions"
    if not bundles_root.is_dir():
        bundles_root = submissions_dir
    return sorted(
        (
            path
            for path in bundles_root.iterdir()
            if path.is_dir() and (path / "submission.yaml").is_file()
        ),
        key=lambda path: path.name,
    )


def _is_eligible(bundle: InteractiveBundle) -> bool:
    """Return whether the bundle measures one of the active leaderboard suites."""
    measured = bundle.manifest.measured
    return (
        measured.suite_name in _ELIGIBLE_SUITES
        and measured.suite_revision >= _MINIMUM_SUITE_REVISION
    )


def _could_be_eligible(bundle_dir: Path) -> bool:
    """Avoid parsing legacy payload schemas that cannot contribute to the active board."""
    raw = yaml.safe_load((bundle_dir / "submission.yaml").read_text())
    if not isinstance(raw, dict):
        raise TypeError(f"{bundle_dir / 'submission.yaml'} is not a mapping")
    measured = raw.get("measured")
    if not isinstance(measured, dict) or measured.get("suite_name") not in _ELIGIBLE_SUITES:
        return False
    revision = measured.get("suite_revision")
    return not isinstance(revision, int) or revision >= _MINIMUM_SUITE_REVISION


def _mean(token_counts: list[int]) -> float:
    """Return a stable zero for a mean over an empty optional role."""
    return sum(token_counts) / len(token_counts) if token_counts else _ZERO_PERCENT


def _percentage(numerator: int, denominator: int) -> float:
    """Return a percentage without failing on an empty experiment payload."""
    return 100 * numerator / denominator if denominator else _ZERO_PERCENT


def _player_payload(player: SubmissionPlayer | None) -> dict[str, Any] | None:
    """Serialise one role's public leaderboard identity and capabilities."""
    if player is None:
        return None
    return {
        "identity": player.identity.model_dump(mode="json"),
        "fingerprint": player.fingerprint,
        "capabilities": player.capabilities.model_dump(mode="json"),
    }


def _module_breakdown(
    experiments: list[SubmissionExperiment],
) -> dict[str, dict[str, float | int]]:
    """Count module appearances and solves from terminal bomb states."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"appearances": 0, "solved": 0})
    for experiment in experiments:
        for module in experiment.final_bomb_state.modules:
            module_counts = counts[str(module.name)]
            module_counts["appearances"] += 1
            module_counts["solved"] += int(module.is_solved)
    return {
        module_name: {
            **module_counts,
            "solved_pct": _percentage(module_counts["solved"], module_counts["appearances"]),
        }
        for module_name, module_counts in sorted(counts.items())
    }


def _entry_payload(bundle: InteractiveBundle) -> dict[str, Any]:
    """Build one website record from an already parsed interactive submission bundle."""
    manifest = bundle.manifest
    experiments = bundle.experiments
    suite = bundle.suite_lock.select_entry(
        manifest.measured.suite_name, manifest.measured.suite_revision
    )
    expert = next((player for player in manifest.players if player.role == "expert"), None)
    module_appearances = sum(
        len(experiment.final_bomb_state.modules) for experiment in experiments
    )
    module_solves = sum(
        experiment.final_bomb_state.num_modules_solved for experiment in experiments
    )
    attempt_count = len(experiments)
    return {
        "bundle": manifest.submission_id,
        "submission_id": manifest.submission_id,
        "suite": {
            "name": manifest.measured.suite_name,
            "revision": manifest.measured.suite_revision,
            "digest": manifest.measured.suite_digest,
            "communication_style": suite.defuser_protocol.communication_style,
            "mission_set": suite.mission_set,
            "modality": list(suite.modality),
        },
        "players": {
            "defuser": _player_payload(manifest.player),
            "expert": _player_payload(expert),
        },
        "provenance": {
            "gptnt_version": manifest.provenance.gptnt_version,
            "run_date": str(manifest.run_date),
            "submitter": manifest.submitter.model_dump(mode="json"),
        },
        "metrics": {
            "attempts": attempt_count,
            "mission_solved_pct": _percentage(
                sum(experiment.final_bomb_state.is_solved for experiment in experiments),
                attempt_count,
            ),
            "module_solved_pct": _percentage(module_solves, module_appearances),
            "any_module_solved_pct": _percentage(
                sum(
                    experiment.final_bomb_state.num_modules_solved > 0
                    for experiment in experiments
                ),
                attempt_count,
            ),
            "mean_strikes": _mean(
                [experiment.final_bomb_state.strike_count for experiment in experiments]
            ),
            "timed_out_pct": _percentage(
                sum(experiment.final_bomb_state.is_timed_out for experiment in experiments),
                attempt_count,
            ),
            "detonated_pct": _percentage(
                sum(experiment.final_bomb_state.is_detonated for experiment in experiments),
                attempt_count,
            ),
        },
        "module_breakdown": _module_breakdown(experiments),
        "usage": {
            "defuser_mean_tokens": _mean(
                [experiment.defuser_usage.total_tokens for experiment in experiments]
            ),
            "expert_mean_tokens": _mean(
                [
                    experiment.expert_usage.total_tokens
                    for experiment in experiments
                    if experiment.expert_usage is not None
                ]
            ),
        },
    }


def _suite_payload(entry: dict[str, Any]) -> dict[str, Any]:
    """Return the active-suite metadata once for the artifact's index."""
    return entry["suite"]


def build_leaderboard(
    submissions_dir: Annotated[Path, Parameter(help="Checkout containing submission bundles.")],
    *,
    output: Annotated[Path, Parameter(help="Path for leaderboard.generated.json")],
    generated_from: Annotated[
        str, Parameter(help="Source revision label recorded in the generated artifact.")
    ] = "local",
) -> None:
    """Build a deterministic website artifact from active interactive submission bundles."""
    entries = [
        _entry_payload(bundle)
        for bundle_dir in _submission_directories(submissions_dir)
        if _could_be_eligible(bundle_dir)
        and isinstance(bundle := load_submission_bundle(bundle_dir), InteractiveBundle)
        and _is_eligible(bundle)
    ]
    entries.sort(
        key=lambda entry: (
            entry["suite"]["name"],
            entry["suite"]["revision"],
            entry["players"]["defuser"]["identity"]["display_name"],
            entry["submission_id"],
        )
    )
    suites = {
        f"{entry['suite']['name']}@{entry['suite']['revision']}": _suite_payload(entry)
        for entry in entries
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_from": generated_from,
                "suites": suites,
                "entries": entries,
            },
            indent=2,
        )
        + "\n"
    )
